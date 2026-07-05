"""parse_resume job (SPEC §8.6.2, §14). Idempotent, retried x3. Never blocks the
candidate flow — terminal failure sets resume_parse_status='failed'."""

from __future__ import annotations

import io

import structlog

from app.core import storage
from app.db.models import FormSubmission, StoredFile
from app.db.session import SessionLocal
from app.llm.clients import resume_extractor
from app.llm.prompts import load_prompt

log = structlog.get_logger(__name__)

_MIN_TEXT_CHARS = 400  # below this → OCR fallback (SPEC §8.6.2)


def _extract_pdf(data: bytes) -> str:
    import fitz  # PyMuPDF  [VERIFY-DOC]

    text_parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
        text = "\n".join(text_parts)
        if len(text.strip()) >= _MIN_TEXT_CHARS:
            return text
        # OCR fallback: rasterize pages and run tesseract.
        import pytesseract  # [VERIFY-DOC]
        from PIL import Image

        ocr_parts: list[str] = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_parts.append(pytesseract.image_to_string(img))
        return "\n".join(ocr_parts)


def _extract_docx(data: bytes) -> str:
    import docx  # python-docx  [VERIFY-DOC]

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)


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
            if stored.mime == "application/pdf":  # type: ignore
                text = _extract_pdf(data)
            else:
                text = _extract_docx(data)

            agent = resume_extractor()
            prompt = load_prompt("extract", "v1").replace("{resume_text}", text[:60000])
            result = await agent.run(prompt)
            parsed = getattr(result, "output", None) or getattr(result, "data", None)
            submission.resume_parsed = parsed.model_dump() if parsed else None
            submission.resume_parse_status = "done"
        except Exception as exc:  # noqa: BLE001
            log.warning("resume_parse_failed", submission_id=submission_id, error=str(exc))
            submission.resume_parse_status = "failed"
        await db.commit()
