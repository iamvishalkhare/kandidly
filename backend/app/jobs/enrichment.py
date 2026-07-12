"""enrich_sources job (SPEC §8.6, §14). Scrapes the candidate's GitHub / website
/ blog links from their form answers and persists a per-source digest on the
form submission. Best effort, idempotent — never blocks plan generation or the
interview (generate_plan only *waits* for a terminal enrichment_status)."""

from __future__ import annotations

import structlog
from sqlalchemy import select

from app.db.models import FormSubmission, FormTemplate, Interview
from app.db.session import SessionLocal
from app.domain.enrichment import scrape_sources, select_sources

log = structlog.get_logger(__name__)


async def enrich_sources(ctx: dict, interview_id: str) -> None:
    # Phase 1: read inputs, claim the row (processing).
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            return
        submission = (
            await db.execute(
                select(FormSubmission).where(
                    FormSubmission.application_id == interview.application_id
                )
            )
        ).scalar_one_or_none()
        if submission is None:
            return
        if submission.enrichment_status == "done":
            return  # idempotent
        template = await db.get(FormTemplate, submission.template_id)
        submission_id = submission.id
        answers = dict(submission.answers or {})
        field_hints = dict(template.field_hints or {}) if template else {}
        submission.enrichment_status = "processing"
        await db.commit()

    sources = select_sources(answers, field_hints)

    # Phase 2: scrape outside the transaction (network-bound). Never raises.
    results = await scrape_sources(sources) if sources else []

    # Phase 3: persist.
    async with SessionLocal() as db:
        sub = await db.get(FormSubmission, submission_id)
        if sub is None:
            return
        sub.enrichment = {"sources": results}
        if not sources:
            sub.enrichment_status = "skipped"
        elif any(r.get("status") == "done" for r in results):
            sub.enrichment_status = "done"
        else:
            sub.enrichment_status = "failed"
        await db.commit()
        log.info(
            "enrich_sources_done",
            interview_id=interview_id,
            n_sources=len(sources),
            status=sub.enrichment_status,
        )
