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


@dataclass
class ImageInput:
    """An image stream selected for conversion to PDF."""

    name: str
    stream: BinaryIO


@dataclass
class ImageToPDFOutput:
    """Result from converting image streams into a single PDF."""

    buffer: Optional[io.BytesIO]
    processed_count: int
    skipped_count: int
    skipped_files: List[str]

    @property
    def has_output(self) -> bool:
        return self.buffer is not None and self.processed_count > 0


@dataclass
class CompressOutput:
    """Result from compressing a single PDF."""

    buffer: Optional[io.BytesIO]
    pages: int
    skipped: bool
    skipped_reason: Optional[str]
    source_name: str

    @property
    def has_output(self) -> bool:
        return self.buffer is not None and not self.skipped


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


def images_to_pdf_streams(inputs: Iterable[ImageInput]) -> ImageToPDFOutput:
    """Convert image streams into a single in-memory PDF document."""

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - import guard kept for CLI compatibility
        raise RuntimeError(
            "Pillow is required. Install with: python -m pip install Pillow"
        ) from exc

    processed_entries: List[tuple[str, "Image.Image"]] = []
    skipped_files: List[str] = []

    for image_input in inputs:
        stream = image_input.stream
        try:
            stream.seek(0)
        except Exception:
            stream = io.BytesIO(stream.read())  # type: ignore[arg-type]
            image_input.stream = stream

        try:
            stream.seek(0)
            with Image.open(stream) as opened:
                opened.load()
                if opened.mode != "RGB":
                    image = opened.convert("RGB")
                else:
                    image = opened.copy()
        except Exception:
            skipped_files.append(image_input.name)
            continue

        processed_entries.append((image_input.name, image))

    processed_count = len(processed_entries)
    skipped_count = len(skipped_files)

    if processed_count == 0:
        return ImageToPDFOutput(
            buffer=None,
            processed_count=0,
            skipped_count=skipped_count,
            skipped_files=skipped_files,
        )

    output_buffer = io.BytesIO()

    _, first_image = processed_entries[0]
    remaining_images = [image for _, image in processed_entries[1:]]

    try:
        if remaining_images:
            first_image.save(
                output_buffer,
                format="PDF",
                save_all=True,
                append_images=remaining_images,
            )
        else:
            first_image.save(output_buffer, format="PDF")
    except Exception:
        output_buffer.close()
        for _, image in processed_entries:
            image.close()
        return ImageToPDFOutput(
            buffer=None,
            processed_count=0,
            skipped_count=skipped_count + processed_count,
            skipped_files=skipped_files
            + [name for name, _ in processed_entries],
        )

    output_buffer.seek(0)

    for _, image in processed_entries:
        image.close()

    return ImageToPDFOutput(
        buffer=output_buffer,
        processed_count=processed_count,
        skipped_count=skipped_count,
        skipped_files=skipped_files,
    )


def compress_pdf_stream(
    pdf_input: PDFInput,
    default_password: Optional[str] = None,
) -> CompressOutput:
    """
    Re-write a PDF with compressed content streams.

    This preserves pages but drops metadata to save a few bytes.
    """

    stream = pdf_input.stream
    try:
        stream.seek(0)
    except Exception:
        stream = io.BytesIO(stream.read())  # type: ignore[arg-type]
        pdf_input.stream = stream

    try:
        stream.seek(0)
        reader = PdfReader(stream)
    except Exception:
        return CompressOutput(
            buffer=None,
            pages=0,
            skipped=True,
            skipped_reason="Unable to read PDF",
            source_name=pdf_input.name,
        )

    if getattr(reader, "is_encrypted", False):
        passwords = _passwords_to_try(pdf_input, default_password)
        unlocked = False
        for password in passwords:
            if password and try_decrypt(reader, password):
                unlocked = True
                break
        if not unlocked:
            return CompressOutput(
                buffer=None,
                pages=0,
                skipped=True,
                skipped_reason="Password required or incorrect",
                source_name=pdf_input.name,
            )

    writer = PdfWriter()
    pages = 0

    for page in reader.pages:
        try:
            page.compress_content_streams()  # type: ignore[func-returns-value]
        except Exception:
            # If compression fails for a page, still include it uncompressed.
            pass
        writer.add_page(page)
        pages += 1

    # Drop metadata to avoid carrying over extra bytes.
    try:
        writer.remove_metadata()  # PyPDF2 >= 3.0
    except Exception:
        try:
            writer.add_metadata({})  # Fallback for older versions
        except Exception:
            pass

    output_buffer = io.BytesIO()
    try:
        writer.write(output_buffer)
    except Exception:
        return CompressOutput(
            buffer=None,
            pages=pages,
            skipped=True,
            skipped_reason="Failed to write compressed PDF",
            source_name=pdf_input.name,
        )

    output_buffer.seek(0)
    return CompressOutput(
        buffer=output_buffer,
        pages=pages,
        skipped=False,
        skipped_reason=None,
        source_name=pdf_input.name,
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
