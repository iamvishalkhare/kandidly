"""parse_resume job (SPEC §8.6.2, §14). Idempotent, retried x3. Never blocks the
candidate flow — terminal failure sets resume_parse_status='failed'.

Converts the uploaded PDF/DOCX to Markdown locally — no LLM: pymupdf4llm for PDFs
(headings, lists, tables), mammoth for .docx, with a tesseract OCR fallback for
scanned PDFs. The Markdown is the sole resume representation; both downstream
consumers (plan generator, live interviewer) are LLMs, so a structured JSON parse
buys nothing and is fragile across formats. Stored on
FormSubmission.resume_markdown (Postgres = source of truth); it rides into the
Redis interview-context cache from there (see domain/interview_context.py)."""

from __future__ import annotations

import io

import structlog

from app.core import storage
from app.db.models import FormSubmission, StoredFile
from app.db.session import SessionLocal

log = structlog.get_logger(__name__)

_MIN_TEXT_CHARS = 400  # below this a PDF is treated as scanned → OCR fallback


def _pdf_to_markdown(data: bytes) -> str:
    """PDF → Markdown via pymupdf4llm; OCR fallback for scanned/image-only PDFs."""
    import fitz  # PyMuPDF
    import pymupdf4llm

    with fitz.open(stream=data, filetype="pdf") as doc:
        md = pymupdf4llm.to_markdown(doc, show_progress=False)
        if len(md.strip()) >= _MIN_TEXT_CHARS:
            return md
        # Scanned/image-only PDF: rasterize each page and OCR it.
        import pytesseract
        from PIL import Image

        ocr_pages: list[str] = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            ocr_pages.append(
                pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))))
            )
        return "\n\n".join(ocr_pages)


def _docx_to_markdown(data: bytes) -> str:
    """DOCX → Markdown via mammoth (preserves headings, lists, tables)."""
    import mammoth

    return mammoth.convert_to_markdown(io.BytesIO(data)).value


def resume_to_markdown(mime: str, data: bytes) -> str:
    """Convert a resume file to Markdown, dispatching by MIME type."""
    if mime == "application/pdf":
        return _pdf_to_markdown(data)
    return _docx_to_markdown(data)


async def parse_resume(ctx: dict, submission_id: str) -> None:
    async with SessionLocal() as db:
        submission = await db.get(FormSubmission, submission_id)
        if submission is None or submission.resume_file_id is None:
            return
        if submission.resume_parse_status == "done":
            return  # idempotent
        submission.resume_parse_status = "processing"
        await db.commit()

        stored = await db.get(StoredFile, submission.resume_file_id)
        data = await storage.get_object(stored.bucket, stored.key)  # type: ignore

        try:
            markdown = resume_to_markdown(stored.mime, data).strip()  # type: ignore
            if not markdown:
                raise ValueError("no text could be extracted from the document")
            submission.resume_markdown = markdown
            submission.resume_parse_status = "done"
            log.info("resume_markdown_ready", submission_id=submission_id, chars=len(markdown))
        except Exception as exc:  # noqa: BLE001
            log.warning("resume_parse_failed", submission_id=submission_id, error=str(exc))
            submission.resume_parse_status = "failed"
        await db.commit()
