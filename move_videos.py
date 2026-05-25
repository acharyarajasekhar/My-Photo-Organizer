#!/usr/bin/env python3
"""
move_videos.py

Recursively find video files and move them into a target folder (default:
`Organized_Albums/Videos` under the provided root). Supports `--preserve-structure`,
`--copy` (keep originals), `--dry-run`, and `--verbose`.

Usage examples:
  python move_videos.py --dir . --dry-run
  python move_videos.py --dir C:\Photos --preserve-structure
  python move_videos.py --dir C:\Photos --copy
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Move video files into a target folder.")
    p.add_argument("--dir", "-d", default=".", help="Directory to scan")
    p.add_argument(
        "--target",
        "-t",
        default=None,
        help=("Target folder to move videos into. If relative, interpreted relative to --dir. "
              "Default: Organized_Albums/Videos under --dir."),
    )
    p.add_argument(
        "--extensions",
        "-e",
        default="mp4,mov,m4v,avi,mkv,webm,3gp,wmv,flv",
        help="Comma-separated list of video extensions (no dots).",
    )
    p.add_argument("--preserve-structure", action="store_true", help="Preserve relative subfolder structure under target")
    p.add_argument("--copy", action="store_true", help="Copy files instead of moving (keep originals)")
    p.add_argument("--dry-run", action="store_true", help="Show actions without performing them")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    p.add_argument("--include-organized", action="store_true", help="Include files already under Organized_Albums")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    base_dir = os.path.abspath(args.dir)
    if not os.path.isdir(base_dir):
        logging.error("Not a directory: %s", base_dir)
        return 2

    if args.target:
        target = args.target if os.path.isabs(args.target) else os.path.abspath(os.path.join(base_dir, args.target))
    else:
        target = os.path.join(base_dir, "Organized_Albums", "Videos")

    _ensure_dir(target)
    organized_dir = os.path.join(base_dir, "Organized_Albums")

    exts = set()
    for part in args.extensions.split(','):
        pext = part.strip().lstrip('.').lower()
        if pext:
            exts.add('.' + pext)

    scanned = 0
    moved = 0
    skipped = 0

    for root, _, files in os.walk(base_dir):
        for fname in files:
            scanned += 1
            full = os.path.join(root, fname)

            # Skip files under Organized_Albums by default
            try:
                if not args.include_organized and os.path.commonpath([os.path.abspath(full), os.path.abspath(organized_dir)]) == os.path.abspath(organized_dir):
                    logging.debug("Skipping (under Organized_Albums): %s", full)
                    skipped += 1
                    continue
            except Exception:
                pass

            ext = os.path.splitext(fname)[1].lower()
            if ext not in exts:
                continue

            if args.preserve_structure:
                rel = os.path.relpath(root, base_dir)
                dest_dir = os.path.join(target, rel)
                dest = os.path.join(dest_dir, fname)
            else:
                dest_dir = target
                dest = os.path.join(dest_dir, fname)

            # Avoid moving a file onto itself
            try:
                if os.path.abspath(full) == os.path.abspath(dest):
                    logging.debug("Already at destination: %s", full)
                    skipped += 1
                    continue
            except Exception:
                pass

            _ensure_dir(os.path.dirname(dest))

            # Collision handling: append _1, _2, ...
            if os.path.exists(dest):
                base_name, extn = os.path.splitext(dest)
                i = 1
                new_dest = dest
                while os.path.exists(new_dest):
                    new_dest = f"{base_name}_{i}{extn}"
                    i += 1
                dest = new_dest

            if args.dry_run:
                if args.copy:
                    print("[DRY RUN] Would copy:", full, "->", dest)
                else:
                    print("[DRY RUN] Would move:", full, "->", dest)
                moved += 1
                continue

            try:
                if args.copy:
                    shutil.copy2(full, dest)
                    print("Copied:", full, "->", dest)
                else:
                    shutil.move(full, dest)
                    print("Moved:", full, "->", dest)
                moved += 1
            except Exception as e:
                logging.warning("Failed to move/copy %s: %s", full, e)

    print(f"Scanned {scanned} files; moved/copied {moved}; skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
