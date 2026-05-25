#!/usr/bin/env python3
"""
delete_screenshots.py

Recursively delete files whose basenames start with a given prefix
(default: "Screenshot"). Safe-by-default: skips files under
`Organized_Albums` unless `--include-organized` is set. Supports
`--dry-run` and `--verbose`.

Usage:
  python delete_screenshots.py --dir /path/to/photos [--prefix Screenshot] [--include-organized] [--dry-run] [--verbose]
"""
from __future__ import annotations

import os
import argparse
import logging
import sys


def _is_under(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(parent)]) == os.path.abspath(parent)
    except Exception:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Recursively delete files whose basenames start with a prefix.")
    p.add_argument("--dir", "-d", default=".", help="Directory to scan")
    p.add_argument("--prefix", "-p", default="Screenshot", help="Filename prefix to match (case-insensitive)")
    p.add_argument("--include-organized", action="store_true", help="Include files under Organized_Albums")
    p.add_argument("--dry-run", action="store_true", help="Show actions without deleting files")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    base_dir = os.path.abspath(args.dir)
    if not os.path.isdir(base_dir):
        logging.error("Not a directory: %s", base_dir)
        return 2

    prefix = args.prefix or ""
    prefix_lower = prefix.lower()
    organized_dir = os.path.join(base_dir, "Organized_Albums")

    total_scanned = 0
    matches: list[str] = []

    for root, _, files in os.walk(base_dir):
        for fname in files:
            total_scanned += 1
            full = os.path.join(root, fname)

            # Optionally skip anything inside Organized_Albums by default
            if not args.include_organized and _is_under(full, organized_dir):
                logging.debug("Skipping (under Organized_Albums): %s", full)
                continue

            try:
                if fname.lower().startswith(prefix_lower):
                    matches.append(full)
                    if args.dry_run:
                        print("[DRY RUN] Would delete:", full)
                    else:
                        try:
                            os.remove(full)
                            print("Deleted:", full)
                        except Exception as e:
                            logging.warning("Failed to delete %s: %s", full, e)
            except Exception:
                logging.debug("Error inspecting file: %s", full)

    print(f"Scanned {total_scanned} files; matched {len(matches)} files (prefix='{prefix}').")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
