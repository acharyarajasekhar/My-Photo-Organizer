#!/usr/bin/env python3
"""
organize_photos.py

Scan a Google Photos backup, cluster images by time+location, and ask a
local LLaVA model (via Ollama) to suggest short album titles.

Usage: python organize_photos.py --dir ./my_google_photos
"""
import os
import glob
import math
import argparse
import logging
import shutil
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

try:
    import ollama
except Exception:
    ollama = None

try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None


def _rational_to_float(r):
    try:
        # PIL may return rational as (num, den)
        if hasattr(r, "numerator") and hasattr(r, "denominator"):
            return float(r.numerator) / float(r.denominator)
        if isinstance(r, tuple) and len(r) == 2:
            return float(r[0]) / float(r[1])
        return float(r)
    except Exception:
        return None


def _dms_to_dd(dms, ref):
    try:
        d = _rational_to_float(dms[0])
        m = _rational_to_float(dms[1])
        s = _rational_to_float(dms[2])
        dd = d + (m / 60.0) + (s / 3600.0)
        if ref in ("S", "W"):
            dd = -dd
        return dd
    except Exception:
        return None


def get_exif_data(path):
    """Return (datetime, (lat, lon)) or (None, (None, None))."""
    try:
        img = Image.open(path)
        exif = img._getexif()

        # normalize EXIF dict (may be None)
        exif_data = {}
        if exif:
            for tag, value in exif.items():
                decoded = TAGS.get(tag, tag)
                exif_data[decoded] = value

        # Timestamp: prefer EXIF tags when present
        dt = None
        for tag in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            if tag in exif_data:
                val = exif_data[tag]
                if isinstance(val, bytes):
                    try:
                        val = val.decode(errors="ignore")
                    except Exception:
                        val = str(val)
                try:
                    dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                except Exception:
                    if date_parser:
                        try:
                            dt = date_parser.parse(str(val))
                        except Exception:
                            dt = None
                if dt:
                    break

        # If no EXIF timestamp found, try to parse a date from the filename
        # (e.g. 20221001, 2022-10-01, IMG_20221001_1234).
        if not dt:
            try:
                import re

                name = os.path.basename(path)
                candidates = []
                # Common ISO-like patterns: YYYYMMDD or YYYY-MM-DD / YYYY_MM_DD / YYYY.MM.DD
                for m in re.finditer(r"\d{4}[-_.]?\d{2}[-_.]?\d{2}", name):
                    candidates.append(m.group(0))
                # Day-first patterns like DD-MM-YYYY
                for m in re.finditer(r"\d{2}[-_.]?\d{2}[-_.]?\d{4}", name):
                    candidates.append(m.group(0))
                # Any remaining 8-digit sequences
                for m in re.finditer(r"\d{8}", name):
                    if m.group(0) not in candidates:
                        candidates.append(m.group(0))

                parsed = None
                for cand in candidates:
                    try:
                        if date_parser:
                            try:
                                parsed = date_parser.parse(cand, fuzzy=False, dayfirst=False)
                            except Exception:
                                try:
                                    parsed = date_parser.parse(cand, fuzzy=False, dayfirst=True)
                                except Exception:
                                    parsed = None
                        else:
                            # Basic parsing when dateutil not available
                            if re.match(r"^\d{8}$", cand):
                                y = int(cand[0:4])
                                mth = int(cand[4:6])
                                d = int(cand[6:8])
                                parsed = datetime(y, mth, d)
                            else:
                                parts = re.split(r"[-_.]", cand)
                                if len(parts) == 3:
                                    if len(parts[0]) == 4:
                                        y = int(parts[0]); mth = int(parts[1]); d = int(parts[2])
                                        parsed = datetime(y, mth, d)
                                    else:
                                        d = int(parts[0]); mth = int(parts[1]); y = int(parts[2])
                                        parsed = datetime(y, mth, d)
                    except Exception:
                        parsed = None

                    if parsed:
                        dt = parsed
                        break
            except Exception as e:
                logging.debug("Filename date parse failed for %s: %s", path, e)

        # GPS
        lat = lon = None
        gps_info = exif_data.get("GPSInfo")
        if gps_info:
            gps_parsed = {}
            for t in gps_info:
                sub_decoded = GPSTAGS.get(t, t)
                gps_parsed[sub_decoded] = gps_info[t]

            if (
                "GPSLatitude" in gps_parsed
                and "GPSLatitudeRef" in gps_parsed
                and "GPSLongitude" in gps_parsed
                and "GPSLongitudeRef" in gps_parsed
            ):
                lat = _dms_to_dd(gps_parsed["GPSLatitude"], gps_parsed["GPSLatitudeRef"])
                lon = _dms_to_dd(gps_parsed["GPSLongitude"], gps_parsed["GPSLongitudeRef"])

        return dt, (lat, lon)
    except Exception as e:
        logging.debug("EXIF parse error for %s: %s", path, e)
        return None, (None, None)


def haversine_meters(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_photos(directory, exts=None):
    if exts is None:
        exts = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".heic", ".HEIC"}
    else:
        exts = set(e.lower() for e in exts)
    files = []
    for root, _, filenames in os.walk(directory):
        for fname in filenames:
            _, ext = os.path.splitext(fname)
            if ext.lower() in exts:
                files.append(os.path.join(root, fname))
    return files

def cluster_photos(directory, time_threshold_hours=3.0, dist_threshold_m=1000.0):
    files = find_photos(directory)
    photos = []
    undated = []
    for f in files:
        dt, (lat, lon) = get_exif_data(f)
        if dt:
            photos.append({"path": f, "datetime": dt, "lat": lat, "lon": lon})
        else:
            logging.debug("No EXIF timestamp, will mark undated: %s", f)
            undated.append({"path": f})

    photos.sort(key=lambda x: x["datetime"])

    clusters = []
    current = []
    for p in photos:
        if not current:
            current.append(p)
            continue
        last = current[-1]
        time_diff = (p["datetime"] - last["datetime"]).total_seconds() / 3600.0
        time_ok = time_diff <= time_threshold_hours

        geo_ok = True
        if p["lat"] is not None and last["lat"] is not None:
            dist = haversine_meters(p["lat"], p["lon"], last["lat"], last["lon"])
            geo_ok = dist <= dist_threshold_m

        if time_ok and geo_ok:
            current.append(p)
        else:
            clusters.append(current)
            current = [p]

    if current:
        clusters.append(current)

    return clusters, undated


def sanitize_title(text):
    if not text:
        return "Unnamed_Event"
    s = str(text).strip().splitlines()[0]
    s = s.strip().strip('"').strip("'")
    import re

    s = re.sub(r"[\\/<>:?*|\"]+", "", s)
    s = re.sub(r"[\n\r]+", " ", s).strip()
    parts = s.split()
    s = " ".join(parts[:4])
    if not s:
        s = "Unnamed_Event"
    return s.replace("/", "-")


def ask_llava_for_album_name(sample_paths, model="llava", max_images=3, host=None):
    imgs = sample_paths[:max_images]

    # Build additional context from current parent folder names (deduplicated, limited)
    parent_names = []
    for p in imgs:
        try:
            parent = os.path.basename(os.path.dirname(os.path.abspath(p))) or "."
        except Exception:
            parent = "."
        parent_names.append(parent)
    # preserve order, dedupe
    seen = set()
    unique_parents = []
    for n in parent_names:
        if n not in seen:
            seen.add(n)
            unique_parents.append(n)
    if unique_parents:
        folders_str = ", ".join(unique_parents[:6])
        extra_context = (
            f"Context: these files currently live in folders: {folders_str}. "
            "Use these folder names as additional context when choosing a concise title. "
        )
    else:
        extra_context = ""

    prompt = (
        "These images were taken at the same event. Provide a concise 2-4 word "
        "title suitable as a folder name for these photos. "
        + extra_context
        + "Respond ONLY with the title."
    )

    def _extract_text(obj):
        """Recursively find a reasonable text string in nested response structures."""
        if obj is None:
            return None
        if isinstance(obj, str):
            s = obj.strip()
            if s:
                return s
            return None
        # If it's an object with attributes (e.g., pydantic model), try common attrs
        # Check before dict/list handling so objects with .dict() are handled.
        try:
            for attr in ("response", "message", "text", "content", "output", "result"):
                if hasattr(obj, attr):
                    try:
                        return _extract_text(getattr(obj, attr))
                    except Exception:
                        pass
            # Pydantic / client objects often expose dict/json/model_dump methods
            for meth in ("model_dump", "dict", "model_dump_json", "json", "model_dump"):
                if hasattr(obj, meth):
                    try:
                        val = getattr(obj, meth)
                        dumped = val() if callable(val) else val
                        # If JSON string, try to parse
                        if isinstance(dumped, str):
                            try:
                                import json as _json

                                parsed = _json.loads(dumped)
                                res = _extract_text(parsed)
                                if res:
                                    return res
                            except Exception:
                                pass
                        res = _extract_text(dumped)
                        if res:
                            return res
                    except Exception:
                        pass
        except Exception:
            pass
        if isinstance(obj, dict):
            # common fields that may contain text
            for key in ("content", "text", "message", "response", "output", "result", "choices", "messages"):
                if key in obj:
                    v = obj[key]
                    # if message is dict with content
                    if isinstance(v, dict) and "content" in v:
                        return _extract_text(v["content"])
                    res = _extract_text(v)
                    if res:
                        return res
            # fallback to scanning values
            for v in obj.values():
                res = _extract_text(v)
                if res:
                    return res
            return None
        if isinstance(obj, (list, tuple)):
            for item in obj:
                res = _extract_text(item)
                if res:
                    return res
        # unknown types: try string conversion
        try:
            s = str(obj)
            if s:
                try:
                    import re

                    m = re.search(r"response\s*=\s*(['\"])(.*?)\1", s)
                    if m:
                        return m.group(2).strip()
                except Exception:
                    pass
                return s.strip()
            return None
        except Exception:
            return None

    try:
        if ollama:
            try:
                response = ollama.generate(model=model, prompt=prompt, images=imgs, stream=False)
            except TypeError:
                client = ollama.Client()
                response = client.generate(model=model, prompt=prompt, images=imgs, stream=False)

            text = _extract_text(response)
            if not text:
                # last resort: stringified response
                text = str(response)
            return sanitize_title(text)

        else:
            # HTTP fallback if requests available
            try:
                import requests
                import base64

                base = (host.rstrip("/") if host else "http://localhost:11434")
                url = base + "/api/generate"
                images_payload = []
                for p in imgs:
                    with open(p, "rb") as fh:
                        images_payload.append({"name": os.path.basename(p), "data": base64.b64encode(fh.read()).decode("utf-8")})
                payload = {"model": model, "prompt": prompt, "images": images_payload}
                r = requests.post(url, json=payload, timeout=120)
                r.raise_for_status()
                data = r.json()
                text = _extract_text(data)
                if not text:
                    text = str(data)
                return sanitize_title(text)
            except Exception as e:
                logging.warning("Ollama HTTP fallback failed: %s", e)
                return "Unnamed_Event"

    except Exception as e:
        logging.exception("LLaVA error: %s", e)
        return "Unnamed_Event"


def organize(directory, time_threshold_hours, dist_threshold_m, max_samples, model, host, copy_files=True, dry_run=False, use_ai=True):
    clusters, undated = cluster_photos(directory, time_threshold_hours, dist_threshold_m)
    print(f"Detected {len(clusters)} event clusters.")
    if undated:
        print(f"Detected {len(undated)} undated photos (no EXIF timestamp); these will be placed in 'Unknown_Date' and will not be sent to AI.")
    target_root = os.path.join(directory, "Organized_Albums")
    os.makedirs(target_root, exist_ok=True)

    for idx, cluster in enumerate(clusters, start=1):
        sample_paths = [p["path"] for p in cluster[:max_samples]]
        date_str = cluster[0]["datetime"].strftime("%Y-%m-%d")

        if use_ai:
            ai_title = ask_llava_for_album_name(sample_paths, model=model, max_images=max_samples, host=host)
        else:
            ai_title = f"Event_{idx}"

        final_album_name = f"{date_str} - {ai_title}"
        print(f"\nProcessing Album {idx}/{len(clusters)} ({len(cluster)} photos): {final_album_name}")

        target_folder = os.path.join(target_root, final_album_name)
        if dry_run:
            print("[DRY RUN] Would create:", target_folder)
            continue
        os.makedirs(target_folder, exist_ok=True)

        for p in cluster:
            try:
                dest = os.path.join(target_folder, os.path.basename(p["path"]))
                if copy_files:
                    shutil.copy2(p["path"], dest)
                else:
                    shutil.move(p["path"], dest)
            except Exception as e:
                logging.warning("Failed to copy/move %s: %s", p["path"], e)

    # Handle undated photos: place in Unknown_Date album and skip AI labeling
    if undated:
        unknown_name = "Unknown_Date"
        unknown_folder = os.path.join(target_root, unknown_name)
        print(f"\nProcessing Undated Photos ({len(undated)} photos): {unknown_name}")
        if dry_run:
            print("[DRY RUN] Would create:", unknown_folder)
            for u in undated:
                print("[DRY RUN] Would copy:", u["path"], "->", os.path.join(unknown_folder, os.path.basename(u["path"])))
        else:
            os.makedirs(unknown_folder, exist_ok=True)
            for u in undated:
                try:
                    dest = os.path.join(unknown_folder, os.path.basename(u["path"]))
                    if copy_files:
                        shutil.copy2(u["path"], dest)
                    else:
                        shutil.move(u["path"], dest)
                except Exception as e:
                    logging.warning("Failed to copy/move undated %s: %s", u["path"], e)

    print("\nPhoto organization complete. Check the 'Organized_Albums' folder.")


def parse_args():
    p = argparse.ArgumentParser(description="Organize Google Photos backup into event albums.")
    p.add_argument("--dir", "-d", default=".", help="Photo backup directory")
    p.add_argument("--time-hours", type=float, default=3.0, help="Time gap (hours) to join into same event")
    p.add_argument("--dist-meters", type=float, default=1000.0, help="Distance (meters) to join into same event")
    p.add_argument("--max-samples", type=int, default=3, help="How many images to send to LLaVA for naming")
    p.add_argument("--model", default="llava", help="Ollama model to use for labeling")
    p.add_argument("--host", default="http://localhost:11434", help="Ollama host (HTTP fallback)")
    p.add_argument("--move", action="store_true", help="Move files instead of copying")
    p.add_argument("--dry-run", action="store_true", help="Show actions without creating folders")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.add_argument("--no-ai", action="store_true", help="Skip AI labeling (use simple titles)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    organize(
        args.dir,
        args.time_hours,
        args.dist_meters,
        args.max_samples,
        args.model,
        args.host,
        copy_files=not args.move,
        dry_run=args.dry_run,
        use_ai=(not args.no_ai),
    )

