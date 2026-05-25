#!/usr/bin/env python3
"""
Create a small set of JPEG images with EXIF DateTimeOriginal and GPS for testing.
"""
import os
import argparse
from PIL import Image
import piexif


def dms_rational(dec):
    dec_abs = abs(float(dec))
    deg = int(dec_abs)
    minutes_full = (dec_abs - deg) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60, 2)
    return [(deg, 1), (minutes, 1), (int(seconds * 100), 100)]


def make_jpeg(path, color, date_str, lat, lon):
    img = Image.new("RGB", (800, 600), color=color)
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    # DateTimeOriginal
    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_str

    # GPS
    lat_ref = "N" if lat >= 0 else "S"
    lon_ref = "E" if lon >= 0 else "W"
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_ref
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = dms_rational(lat)
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lon_ref
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = dms_rational(lon)

    exif_bytes = piexif.dump(exif_dict)
    img.save(path, "jpeg", exif=exif_bytes)


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    samples = [
        ("event1_1.jpg", (200, 100, 100), "2022:10:01 12:00:00", 37.7749, -122.4194),
        ("event1_2.jpg", (100, 200, 100), "2022:10:01 12:05:00", 37.7750, -122.4195),
        ("event1_3.jpg", (100, 100, 200), "2022:10:01 12:10:00", 37.7751, -122.4193),
        ("event2_1.jpg", (240, 240, 120), "2022:10:02 18:00:00", 40.7128, -74.0060),
    ]

    for name, color, dt, lat, lon in samples:
        path = os.path.join(outdir, name)
        make_jpeg(path, color, dt, lat, lon)
        print("Created:", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="test_photos", help="Output directory for sample photos")
    args = parser.parse_args()
    main(args.out)
