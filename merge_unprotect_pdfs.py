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
import fnmatch
import os
import sys
from getpass import getpass
from typing import List, Optional, Tuple

try:
    from PyPDF2 import PdfReader, PdfWriter
except Exception as e:
    print("PyPDF2 is required. Install with: python -m pip install PyPDF2", file=sys.stderr)
    raise


def natural_key(s: str):
    """Sort helper that treats digits as numbers: file2 < file10 < file100."""
    import re
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def discover_pdfs(folder: str, recursive: bool, pattern: str) -> List[str]:
    folder = os.path.abspath(folder)
    matches: List[str] = []
    if recursive:
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".pdf") and fnmatch.fnmatch(f, pattern):
                    matches.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            if f.lower().endswith(".pdf") and fnmatch.fnmatch(f, pattern):
                matches.append(os.path.join(folder, f))
    return matches


def try_decrypt(reader: PdfReader, password: str) -> bool:
    """
    Decrypt that works across PyPDF2 versions.
    Old versions return 0/1/2; newer return True/False.
    """
    try:
        res = reader.decrypt(password)  # type: ignore[attr-defined]
        if isinstance(res, bool):
            return res
        try:
            return bool(int(res))
        except Exception:
            return False
    except Exception:
        return False


def merge_pdfs(
    inputs: List[str],
    output_path: str,
    common_password: Optional[str] = None,
    prompt_missing_passwords: bool = True,
    order_mode: str = "name"
) -> Tuple[int, int]:
    """
    Merge PDFs into output_path.
    Returns (merged_count, skipped_count).
    """
    writer = PdfWriter()

    if order_mode == "mtime":
        inputs.sort(key=lambda p: os.path.getmtime(p))
    else:
        # default: name (natural)
        inputs.sort(key=lambda p: natural_key(os.path.basename(p)))

    merged_count = 0
    skipped_count = 0

    for path in inputs:
        rel = os.path.relpath(path)
        print(f"Processing: {rel}")
        try:
            reader = PdfReader(path)
            if getattr(reader, "is_encrypted", False):
                # attempt common password first
                pw = common_password
                if pw:
                    ok = try_decrypt(reader, pw)
                    if not ok and prompt_missing_passwords:
                        pw = getpass(f"  Password for '{rel}': ")
                        ok = try_decrypt(reader, pw)
                else:
                    if prompt_missing_passwords:
                        pw = getpass(f"  Password for '{rel}': ")
                        ok = try_decrypt(reader, pw)
                    else:
                        ok = False

                if not ok:
                    print(f"  Could not decrypt (wrong/unknown password). Skipping.")
                    skipped_count += 1
                    continue

            # Append pages
            for page in reader.pages:
                writer.add_page(page)
            merged_count += 1

        except KeyboardInterrupt:
            print("\nAborted by user.")
            raise
        except Exception as e:
            print(f"  Failed to read '{rel}': {e}")
            skipped_count += 1

    # Write output ONLY if at least one PDF was merged
    if merged_count > 0:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
            with open(output_path, "wb") as out_f:
                writer.write(out_f)
            print(f"\n✅ Saved merged unlocked PDF to: {output_path}")
        except Exception as e:
            print(f"\n❌ Failed to write output '{output_path}': {e}")
            raise
    else:
        print("\nNo PDFs merged; nothing to write.")

    return merged_count, skipped_count


def main():
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
