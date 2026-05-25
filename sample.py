import os
import glob
import json
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import ollama

# --- CONFIGURATION ---
PHOTO_DIR = "./my_google_photos"  # Path to your photo backup
TIME_THRESHOLD_HOURS = 3          # Maximum gap to consider it the "same event"
MAX_PHOTOS_PER_ALBUM_FOR_AI = 3    # How many images LLaVA should look at to guess the theme

def get_exif_data(image_path):
    """Extracts timestamp and GPS coordinates from image EXIF data."""
    try:
        img = Image.open(image_path)
        exif = img._getexif()
        if not exif:
            return None, None
        
        info = {}
        for tag, value in exif.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                gps_data = {}
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_data[sub_decoded] = value[t]
                info[decoded] = gps_data
            else:
                info[decoded] = value
                
        # Parse Timestamp
        dt = None
        for tag in ['DateTimeOriginal', 'DateTime', 'DigitalZoomRatio']:
            if tag in info:
                try:
                    dt = datetime.strptime(str(info[tag]), '%Y:%m:%d %H:%M:%S')
                    break
                except:
                    continue
                    
        # Parse GPS (Rough convert to decimal for comparison)
        lat, lon = None, None
        if "GPSInfo" in info:
            gps = info["GPSInfo"]
            if "GPSLatitude" in gps and "GPSLongitude" in gps:
                # Basic conversion helper
                def to_dec(dms): return float(dms[0]) + float(dms[1])/60 + float(dms[2])/3600
                lat = to_dec(gps["GPSLatitude"])
                lon = to_dec(gps["GPSLongitude"])
                
        return dt, (lat, lon)
    except Exception:
        return None, None

def cluster_photos():
    """Groups photos mathematically using location data and time thresholds."""
    all_photos = []
    
    # Support jpg, jpeg, png (Note: HEIC files will need preprocessing)
    extensions = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG')
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(PHOTO_DIR, ext)))

    print(f"Scanning {len(files)} photos for metadata...")
    for f in files:
        dt, gps = get_exif_data(f)
        if dt:  # We at least need a timestamp to sort
            all_photos.append({'path': f, 'datetime': dt, 'gps': gps})
            
    # Sort chronologically
    all_photos.sort(key=lambda x: x['datetime'])
    
    albums = []
    current_album = []
    
    for photo in all_photos:
        if not current_album:
            current_album.append(photo)
            continue
            
        last_photo = current_album[-1]
        time_diff = (photo['datetime'] - last_photo['datetime']).total_seconds() / 3600
        
        # Check coordinates if both photos have GPS
        geo_match = True
        if photo['gps'] and last_photo['gps']:
            # Rough bounding box check (~0.01 degree variance is roughly 1.1km)
            lat_diff = abs(photo['gps'][0] - last_photo['gps'][0])
            lon_diff = abs(photo['gps'][1] - last_photo['gps'][1])
            if lat_diff > 0.01 or lon_diff > 0.01:
                geo_match = False
                
        # If it falls within our limits, add to current event album
        if time_diff <= TIME_THRESHOLD_HOURS and geo_match:
            current_album.append(photo)
        else:
            albums.append(current_album)
            current_album = [photo]
            
    if current_album:
        albums.append(current_album)
        
    return albums

def ask_llava_for_album_name(photo_paths):
    """Feeds sample photos from an event to LLaVA to deduce an album name."""
    try:
        prompt = (
            "Analyze these images taken at the exact same family/personal event. "
            "Provide a short, descriptive 2-to-4 word title for an album containing these pictures. "
            "Respond ONLY with the title. Do not say 'Here is your title' or use punctuation."
        )
        
        response = ollama.generate(
            model='llava',
            prompt=prompt,
            images=photo_paths[:MAX_PHOTOS_PER_ALBUM_FOR_AI], # LLaVA accepts an array of images
            stream=False
        )
        return response['response'].strip().replace('"', '').replace('/', '-')
    except Exception as e:
        print(f"LLaVA Error: {e}")
        return "Unnamed_Event"

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    photo_groups = cluster_photos()
    print(f"Detected {len(photo_groups)} distinct events/albums.")
    
    for idx, group in enumerate(photo_groups):
        sample_paths = [p['path'] for p in group]
        date_str = group[0]['datetime'].strftime('%Y-%m-%d')
        
        print(f"\nProcessing Album {idx+1}/{len(photo_groups)} ({len(group)} photos)...")
        
        # Call LLaVA to analyze the content visual makeup
        ai_title = ask_llava_for_album_name(sample_paths)
        final_album_name = f"{date_str} - {ai_title}"
        print(f"-> Suggested Folder Name: {final_album_name}")
        
        # Create folder and move/copy files
        target_folder = os.path.join(PHOTO_DIR, "Organized_Albums", final_album_name)
        os.makedirs(target_folder, exist_ok=True)
        
        for p in group:
            filename = os.path.basename(p['path'])
            # Using copy instead of move to preserve your original backup directory state
            import shutil
            shutil.copy(p['path'], os.path.join(target_folder, filename))
            
    print("\nPhoto organization complete! Check the 'Organized_Albums' directory.")