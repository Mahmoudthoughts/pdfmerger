#!/usr/bin/env python3
"""
merge_unprotect_pdfs.py
--------------------------------
Merge a folder of PDFs (some may be password-protected) into ONE unlocked PDF.

Features:
- Works on Windows/macOS/Linux (Python 3.8+).
- Handles encrypted PDFs: use a common password with --password, or get prompted per-file.
- Skips files with wrong/unknown passwords (continues merging others).
- Stable, human-friendly ordering (natural sort by filename). Optionally, order by mtime.
- Optional recursive search and filename pattern filter.
- Writes a single unlocked output file (no password).

Usage (common cases):
  python merge_unprotect_pdfs.py ./pdfs
  python merge_unprotect_pdfs.py ./pdfs -o merged_unlocked.pdf
  python merge_unprotect_pdfs.py ./pdfs --password "COMMON_PASS"
  python merge_unprotect_pdfs.py ./pdfs --recursive
  python merge_unprotect_pdfs.py ./pdfs --pattern "*.pdf" --order mtime

Install dependency:
  python -m pip install PyPDF2
"""

import argparse
import os
import sys

from pdfmerger.core import discover_pdfs, merge_pdfs


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a folder of PDFs (handles password-protected files) into one unlocked PDF.")
    parser.add_argument("folder", help="Folder containing PDFs to merge")
    parser.add_argument("-o", "--output", default="merged_unlocked.pdf", help="Output PDF path (default: merged_unlocked.pdf)")
    parser.add_argument("--password", help="Common password used by all/most PDFs (optional)")
    parser.add_argument("--no-prompt", action="store_true", help="Do NOT prompt for per-file passwords; skip if common password fails or not provided")
    parser.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    parser.add_argument("--pattern", default="*.pdf", help="Filename pattern to include (default: *.pdf)")
    parser.add_argument("--order", choices=["name", "mtime"], default="name", help="Merge order: natural by filename or by modification time")

    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"Folder not found: {args.folder}", file=sys.stderr)
        sys.exit(1)

    pdfs = discover_pdfs(args.folder, recursive=args.recursive, pattern=args.pattern)
    if not pdfs:
        print("No PDFs found with the given criteria.")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDF(s). Order: {args.order}. Output: {args.output}")
    merged, skipped = merge_pdfs(
        pdfs,
        output_path=args.output,
        common_password=args.password,
        prompt_missing_passwords=not args.no_prompt,
        order_mode=args.order,
    )
    print(f"\nSummary: merged={merged}, skipped={skipped} (total={len(pdfs)})")


if __name__ == "__main__":
    main()
