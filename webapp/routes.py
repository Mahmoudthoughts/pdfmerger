"""Web routes for the PDF merger application."""

from __future__ import annotations

import io
import typing as t

from flask import Blueprint, Response, render_template, request, send_file

from pdfmerger.core import MergeOutput, PDFInput, merge_pdf_streams

bp = Blueprint("routes", __name__)


@bp.get("/")
def home() -> str:
    """Render the application home page."""

    return render_template("home.html")


@bp.get("/merge")
def merge_form() -> str:
    """Render the upload interface for merging PDFs."""

    return render_template("upload.html")


def _extract_per_file_passwords(form_data: t.Mapping[str, str]) -> dict[str, str]:
    """Parse per-file password entries from the submitted form."""

    passwords: dict[str, str] = {}
    prefix = "file_passwords["
    suffix = "]"
    for key, value in form_data.items():
        if key.startswith(prefix) and key.endswith(suffix):
            filename = key[len(prefix) : -len(suffix)]
            if value:
                passwords[filename] = value
    return passwords


@bp.post("/merge")
def merge() -> Response | tuple[str, int]:
    """Accept uploaded PDFs and return the merged output."""

    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        return "No PDF files were uploaded.", 400

    shared_password = request.form.get("shared_password") or None
    per_file_passwords = _extract_per_file_passwords(request.form)

    pdf_inputs: list[PDFInput] = []
    for storage in uploaded_files:
        if not storage.filename:
            continue
        stream = storage.stream
        try:
            stream.seek(0)
        except Exception:
            # Werkzeug's stream objects are typically seekable, but fall back to BytesIO if needed.
            data = storage.read()
            stream = io.BytesIO(data)
        pdf_inputs.append(
            PDFInput(
                name=storage.filename,
                stream=stream,
                password=per_file_passwords.get(storage.filename),
            )
        )

    if not pdf_inputs:
        return "No valid PDF files were provided.", 400

    merge_result: MergeOutput = merge_pdf_streams(pdf_inputs, default_password=shared_password)

    if not merge_result.has_output or merge_result.buffer is None:
        message = "Unable to merge the provided PDFs."
        if merge_result.skipped_files:
            skipped_list = ", ".join(merge_result.skipped_files)
            message = f"Unable to merge the provided PDFs. Skipped: {skipped_list}."
        return message, 400

    response = send_file(
        merge_result.buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="merged_unlocked.pdf",
    )

    if merge_result.skipped_files:
        response.headers["X-PDFMerger-Skipped"] = ",".join(merge_result.skipped_files)
        response.headers["X-PDFMerger-Skipped-Count"] = str(merge_result.skipped_count)

    response.headers["X-PDFMerger-Merged-Count"] = str(merge_result.merged_count)
    return response
