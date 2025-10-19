"""Core utilities for the PDF merger project."""

from .core import (
    MergeOutput,
    PDFInput,
    discover_pdfs,
    merge_pdf_streams,
    merge_pdfs,
    natural_key,
    try_decrypt,
)

__all__ = [
    "MergeOutput",
    "PDFInput",
    "discover_pdfs",
    "merge_pdf_streams",
    "merge_pdfs",
    "natural_key",
    "try_decrypt",
]
