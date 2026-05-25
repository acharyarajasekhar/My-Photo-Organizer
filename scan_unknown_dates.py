#!/usr/bin/env python3
"""
scan_unknown_dates.py

Scan a completed folder tree for images that lack an EXIF timestamp (and
optionally lack a parsable date in the filename). Print a report and
optionally move those files into an `Organized_Albums/Unknown_Date` folder.

Usage:
    python scan_unknown_dates.py --dir /path/to/completed_albums [--no-filename] [--move|--copy] [--dry-run] [--verbose]

Options:
    --no-filename   Do not attempt to parse dates from filenames (only EXIF)
    --move          Move found files into Organized_Albums/Unknown_Date
    --copy          Copy found files into Organized_Albums/Unknown_Date (keep originals)
    --dry-run       Show actions without moving/copying files
    --verbose       Enable debug logging
"""
from __future__ import annotations

import os
import re
import argparse
import logging
import shutil
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS

try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None


def _rational_to_float(r):
    try:
        if hasattr(r, "numerator") and hasattr(r, "denominator"):
            return float(r.numerator) / float(r.denominator)
        if isinstance(r, tuple) and len(r) == 2:
            return float(r[0]) / float(r[1])
        return float(r)
    except Exception:
        return None


def try_parse_date_from_filename(path: str) -> datetime | None:
    name = os.path.basename(path)
    candidates = []
    # YYYY[-_.]?MM[-_.]?DD
    for m in re.finditer(r"\d{4}[-_.]?\d{2}[-_.]?\d{2}", name):
        candidates.append(m.group(0))
    # DD[-_.]?MM[-_.]?YYYY
    for m in re.finditer(r"\d{2}[-_.]?\d{2}[-_.]?\d{4}", name):
        candidates.append(m.group(0))
    # 8-digit sequences
    for m in re.finditer(r"\d{8}", name):
        if m.group(0) not in candidates:
            candidates.append(m.group(0))

    for cand in candidates:
        parsed = None
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
                # basic YYYYMMDD
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
            return parsed

    return None


def get_exif_date(path: str, consider_filename: bool = True) -> datetime | None:
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            exif = {}

        exif_data = {}
        for tag, value in exif.items():
            decoded = TAGS.get(tag, tag)
            exif_data[decoded] = value

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

        if not dt and consider_filename:
            return try_parse_date_from_filename(path)

        return dt
    except Exception as e:
        logging.debug("EXIF parse error for %s: %s", path, e)
        if consider_filename:
            return try_parse_date_from_filename(path)
        return None


def find_images(directory: str, exts=None):
    if exts is None:
        exts = {".jpg", ".jpeg", ".png", ".heic"}
    else:
        exts = set(e.lower() for e in exts)

    files = []
    for root, _, filenames in os.walk(directory):
        for fname in filenames:
            _, ext = os.path.splitext(fname)
            if ext.lower() in exts:
                files.append(os.path.join(root, fname))
    return files


def main():
    p = argparse.ArgumentParser(description="Scan for images missing EXIF date and optionally move or copy them to Unknown_Date.")
    p.add_argument("--dir", "-d", default=".", help="Folder to scan")
    p.add_argument("--no-filename", dest="consider_filename", action="store_false", help="Do NOT attempt to parse date from filename")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--move", action="store_true", help="Move found files into Organized_Albums/Unknown_Date")
    group.add_argument("--copy", action="store_true", help="Copy found files into Organized_Albums/Unknown_Date (keep originals)")
    p.add_argument("--dry-run", action="store_true", help="Show actions without performing them")
    p.add_argument("--verbose", action="store_true", help="Verbose debugging output")
    p.set_defaults(consider_filename=True)
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    root = os.path.abspath(args.dir)
    imgs = find_images(root)
    undated = []

    # Skip files already in an Unknown_Date target
    target_default = os.path.join(root, "Organized_Albums", "Unknown_Date")

    for f in imgs:
        # skip files already under target
        try:
            if os.path.commonpath([os.path.abspath(f), os.path.abspath(target_default)]) == os.path.abspath(target_default):
                logging.debug("Skipping (already in Unknown_Date): %s", f)
                continue
        except Exception:
            pass

        dt = get_exif_date(f, consider_filename=args.consider_filename)
        if not dt:
            undated.append(f)

    print(f"Scanned {len(imgs)} images; found {len(undated)} undated files (consider_filename={args.consider_filename}).")
    if undated:
        for u in undated:
            print(u)

    if (args.move or args.copy) and undated:
        target = target_default
        op = "move" if args.move else "copy"
        if args.dry_run:
            print("[DRY RUN] Would create:", target)
            for u in undated:
                dest = os.path.join(target, os.path.basename(u))
                if args.move:
                    print("[DRY RUN] Would move:", u, "->", dest)
                else:
                    print("[DRY RUN] Would copy:", u, "->", dest)
        else:
            os.makedirs(target, exist_ok=True)
            for u in undated:
                try:
                    dest = os.path.join(target, os.path.basename(u))
                    if os.path.abspath(u) == os.path.abspath(dest):
                        logging.debug("Already at destination: %s", u)
                        continue
                    if args.move:
                        shutil.move(u, dest)
                        print("Moved:", u, "->", dest)
                    else:
                        shutil.copy2(u, dest)
                        print("Copied:", u, "->", dest)
                except Exception as e:
                    logging.warning("Failed to %s %s: %s", op, u, e)


if __name__ == "__main__":
    main()
