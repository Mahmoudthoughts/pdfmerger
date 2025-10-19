"""Shared PDF merger utilities used by both the CLI and web app."""

from __future__ import annotations

import fnmatch
import io
import os
from dataclasses import dataclass
from getpass import getpass
from typing import BinaryIO, Iterable, List, Optional, Sequence, Tuple

try:
    from PyPDF2 import PdfReader, PdfWriter
except Exception as exc:  # pragma: no cover - import guard kept for CLI compatibility
    raise RuntimeError(
        "PyPDF2 is required. Install with: python -m pip install PyPDF2"
    ) from exc


@dataclass
class PDFInput:
    """A PDF input stream with metadata for merging."""

    name: str
    stream: BinaryIO
    password: Optional[str] = None


@dataclass
class MergeOutput:
    """Result from merging PDFs."""

    buffer: Optional[io.BytesIO]
    merged_count: int
    skipped_count: int
    skipped_files: List[str]

    @property
    def has_output(self) -> bool:
        return self.buffer is not None and self.merged_count > 0


def natural_key(value: str) -> List[object]:
    """Sort helper that treats digits numerically: file2 < file10 < file100."""

    import re

    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", value)]


def discover_pdfs(folder: str, recursive: bool, pattern: str) -> List[str]:
    """Return a list of PDFs within *folder* that match *pattern*."""

    folder = os.path.abspath(folder)
    matches: List[str] = []

    if recursive:
        for root, _, files in os.walk(folder):
            for filename in files:
                if filename.lower().endswith(".pdf") and fnmatch.fnmatch(filename, pattern):
                    matches.append(os.path.join(root, filename))
    else:
        for filename in os.listdir(folder):
            if filename.lower().endswith(".pdf") and fnmatch.fnmatch(filename, pattern):
                matches.append(os.path.join(folder, filename))

    return matches


def try_decrypt(reader: PdfReader, password: str) -> bool:
    """Attempt to decrypt *reader* with *password* across PyPDF2 versions."""

    try:
        result = reader.decrypt(password)  # type: ignore[attr-defined]
        if isinstance(result, bool):
            return result
        try:
            return bool(int(result))
        except Exception:
            return False
    except Exception:
        return False


def _passwords_to_try(pdf_input: PDFInput, default_password: Optional[str]) -> List[str]:
    passwords: List[str] = []
    if default_password:
        passwords.append(default_password)
    if pdf_input.password and pdf_input.password not in passwords:
        passwords.append(pdf_input.password)
    return passwords


def merge_pdf_streams(
    inputs: Iterable[PDFInput],
    default_password: Optional[str] = None,
) -> MergeOutput:
    """Merge in-memory PDF streams and return a :class:`MergeOutput`."""

    writer = PdfWriter()
    merged_count = 0
    skipped_count = 0
    skipped_files: List[str] = []

    for pdf_input in inputs:
        stream = pdf_input.stream
        try:
            stream.seek(0)
        except Exception:
            # Some streams may be non-seekable; wrap them in BytesIO for PyPDF2.
            stream = io.BytesIO(stream.read())  # type: ignore[arg-type]
            pdf_input.stream = stream

        try:
            stream.seek(0)
            reader = PdfReader(stream)
        except Exception:
            skipped_count += 1
            skipped_files.append(pdf_input.name)
            continue

        if getattr(reader, "is_encrypted", False):
            passwords = _passwords_to_try(pdf_input, default_password)
            unlocked = False
            for password in passwords:
                if password and try_decrypt(reader, password):
                    unlocked = True
                    break
            if not unlocked:
                skipped_count += 1
                skipped_files.append(pdf_input.name)
                continue

        try:
            for page in reader.pages:
                writer.add_page(page)
        except Exception:
            skipped_count += 1
            skipped_files.append(pdf_input.name)
            continue

        merged_count += 1

    if merged_count == 0:
        return MergeOutput(buffer=None, merged_count=0, skipped_count=skipped_count, skipped_files=skipped_files)

    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    return MergeOutput(
        buffer=output_buffer,
        merged_count=merged_count,
        skipped_count=skipped_count,
        skipped_files=skipped_files,
    )


def merge_pdfs(
    inputs: Sequence[str],
    output_path: str,
    common_password: Optional[str] = None,
    prompt_missing_passwords: bool = True,
    order_mode: str = "name",
) -> Tuple[int, int]:
    """Merge PDFs located at *inputs* into *output_path*."""

    if order_mode == "mtime":
        sorted_inputs = sorted(inputs, key=lambda path: os.path.getmtime(path))
    else:
        sorted_inputs = sorted(inputs, key=lambda path: natural_key(os.path.basename(path)))

    writer = PdfWriter()
    merged_count = 0
    skipped_count = 0

    for path in sorted_inputs:
        rel = os.path.relpath(path)
        print(f"Processing: {rel}")
        try:
            reader = PdfReader(path)
            if getattr(reader, "is_encrypted", False):
                password: Optional[str] = common_password
                unlocked = False

                if password:
                    unlocked = try_decrypt(reader, password)

                while not unlocked and prompt_missing_passwords:
                    password = getpass(f"  Password for '{rel}': ")
                    if not password:
                        break
                    unlocked = try_decrypt(reader, password)

                if not unlocked:
                    print("  Could not decrypt (wrong/unknown password). Skipping.")
                    skipped_count += 1
                    continue

            for page in reader.pages:
                writer.add_page(page)
            merged_count += 1

        except KeyboardInterrupt:
            print("\nAborted by user.")
            raise
        except Exception as exc:
            print(f"  Failed to read '{rel}': {exc}")
            skipped_count += 1

    if merged_count > 0:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
            with open(output_path, "wb") as out_file:
                writer.write(out_file)
            print(f"\n✅ Saved merged unlocked PDF to: {output_path}")
        except Exception as exc:
            print(f"\n❌ Failed to write output '{output_path}': {exc}")
            raise
    else:
        print("\nNo PDFs merged; nothing to write.")

    return merged_count, skipped_count
