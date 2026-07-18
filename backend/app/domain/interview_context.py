"""Interview context bundle (SPEC §9.1) — the consolidated context an AI
interviewer uses to ask better, candidate-specific questions and follow-ups.

Assembles form answers + parsed resume + scraped sources + requisition details
into one dict, caches it in Redis at form submit, and rebuilds it from Postgres
on a cache miss. Read at room load by the agent's bootstrap.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.db.models import (
    FormSubmission,
    FormTemplate,
    Interview,
    QuestionPlan,
    QuestionPlanNode,
    Requisition,
)

log = structlog.get_logger(__name__)

CONTEXT_TTL_SECONDS = 86400  # 24h — covers submit → interview + rejoin grace.
_SKIP_ANSWER_KEYS = {"resume"}  # file field; value is an opaque file id.


def _key(interview_id) -> str:
    return f"interview:context:{interview_id}"


# --------------------------------------------------------------------------- #
# Digest helpers (compact, safe subsets)
# --------------------------------------------------------------------------- #
def _form_digest(answers: dict | None, field_hints: dict | None) -> dict:
    hints = field_hints or {}
    out: dict = {}
    for key, value in (answers or {}).items():
        if key in _SKIP_ANSWER_KEYS or value in (None, "", [], {}):
            continue
        out[key] = {"role": (hints.get(key) or {}).get("role"), "value": value}
    return out


def _requisition_digest(req: Requisition | None) -> dict:
    if req is None:
        return {}
    return {
        "title": req.title,
        "domain": req.domain,
        "role_objective": req.role_objective,
        "technical_requirements": list(req.technical_requirements or []),
        "sample_questions": [
            q.get("text")
            for q in (req.sample_questions or [])
            if isinstance(q, dict) and q.get("text")
        ],
        "interview_type": req.interview_type,
    }


def _seed_questions(plan_nodes: list) -> list[str]:
    """Seed questions from plan nodes (accepts ORM nodes or dicts), excluding
    the wrap / candidate-questions housekeeping nodes."""

    def _get(n, attr):
        return n.get(attr) if isinstance(n, dict) else getattr(n, attr, None)

    return [
        _get(n, "seed_question")
        for n in (plan_nodes or [])
        if _get(n, "seed_question") and _get(n, "node_type") not in ("wrap", "candidate_questions")
    ]


# --------------------------------------------------------------------------- #
# Assembly + cache
# --------------------------------------------------------------------------- #
def assemble_context(
    *,
    req: Requisition | None,
    submission: FormSubmission | None,
    field_hints: dict | None,
    plan_nodes: list | None,
    status: str,
) -> dict:
    """Pure assembly of the context bundle from already-loaded rows."""
    answers = dict(getattr(submission, "answers", None) or {})
    enrichment = getattr(submission, "enrichment", None) or {}
    display_name = answers.get("full_name")

    return {
        "status": status,
        "candidate_display_name": display_name,
        "resume": getattr(submission, "resume_markdown", None),
        "form": _form_digest(answers, field_hints),
        "sources": enrichment.get("sources") or [],
        "requisition": _requisition_digest(req),
        "plan": {"seed_questions": _seed_questions(plan_nodes or [])} if plan_nodes else None,
    }


async def cache_context(interview_id, bundle: dict, ttl: int = CONTEXT_TTL_SECONDS) -> None:
    """Best-effort write — Redis being down must never fail the submit path."""
    try:
        await cache.set_json(_key(interview_id), bundle, ttl)
    except Exception as exc:  # noqa: BLE001
        log.warning("context_cache_write_failed", interview_id=str(interview_id), error=str(exc))


async def get_cached_context(interview_id) -> dict | None:
    try:
        return await cache.get_json(_key(interview_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("context_cache_read_failed", interview_id=str(interview_id), error=str(exc))
        return None


async def invalidate(interview_id) -> None:
    """Drop the cached bundle — used by the console's interview delete."""
    try:
        await cache.delete(_key(interview_id))
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "context_cache_invalidate_failed", interview_id=str(interview_id), error=str(exc)
        )


async def rebuild_context(db: AsyncSession, interview_id) -> dict | None:
    """Reassemble the bundle from Postgres (cache cold-miss path) and re-cache it."""
    interview = await db.get(Interview, interview_id)
    if interview is None:
        return None
    req = await db.get(Requisition, interview.requisition_id)
    submission = (
        await db.execute(
            select(FormSubmission).where(FormSubmission.application_id == interview.application_id)
        )
    ).scalar_one_or_none()
    template = (
        await db.get(FormTemplate, submission.template_id) if submission is not None else None
    )
    plan = (
        await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview_id))
    ).scalar_one_or_none()
    nodes: list = []
    if plan is not None:
        nodes = list(
            (
                await db.execute(
                    select(QuestionPlanNode)
                    .where(QuestionPlanNode.plan_id == plan.id)
                    .order_by(QuestionPlanNode.position)
                )
            )
            .scalars()
            .all()
        )
    bundle = assemble_context(
        req=req,
        submission=submission,
        field_hints=(template.field_hints if template else {}),
        plan_nodes=nodes,
        status="ready" if plan is not None else "partial",
    )
    await cache_context(interview_id, bundle)
    return bundle
