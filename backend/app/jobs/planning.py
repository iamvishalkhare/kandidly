"""generate_plan job (SPEC §14 + §14.1). Waits for resume parse (≤90s), builds
planner inputs, calls the LLM, validates (retry once), else writes a fallback
generic plan. Either way the application reaches plan_ready."""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.models import (
    Application,
    FormSubmission,
    FormTemplate,
    Interview,
    Requisition,
    Rubric,
    RubricCriterion,
)
from app.db.session import SessionLocal
from app.domain import applications as apps
from app.domain.interview_context import assemble_context, cache_context
from app.domain.plan_build import assign_criteria_round_robin, load_fallback, write_plan
from app.domain.plans import validate_plan
from app.llm.clients import plan_generator
from app.llm.prompts import load_prompt, version_tag
from app.schemas.interview_config import InterviewConfig

log = structlog.get_logger(__name__)

_RESUME_WAIT_SECONDS = 90


_TERMINAL = ("done", "failed", "skipped")


async def _wait_for_inputs(db_factory, submission_id) -> None:
    """Wait (≤90s) for the resume parse AND source enrichment to reach a terminal
    state, so the plan is built from the full context. Early-exits when there's
    nothing left to wait for."""
    waited = 0
    while waited < _RESUME_WAIT_SECONDS:
        async with db_factory() as db:
            sub = await db.get(FormSubmission, submission_id)
            if sub is None:
                return
            resume_ready = sub.resume_file_id is None or sub.resume_parse_status in _TERMINAL
            enrichment_ready = sub.enrichment_status in _TERMINAL
            if resume_ready and enrichment_ready:
                return
        await asyncio.sleep(3)
        waited += 3


async def generate_plan(ctx: dict, interview_id: str) -> None:
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            return
        app = await db.get(Application, interview.application_id)
        submission = (
            await db.execute(select(FormSubmission).where(FormSubmission.application_id == app.id))  # type: ignore
        ).scalar_one()
        req = await db.get(Requisition, interview.requisition_id)
        rubric = await db.get(Rubric, req.rubric_id)  # type: ignore
        criteria = (
            (
                await db.execute(
                    select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id)  # type: ignore
                )
            )
            .scalars()
            .all()
        )
        criteria_keys = [c.key for c in criteria]
        template = await db.get(FormTemplate, req.form_template_id)  # type: ignore
        cfg = InterviewConfig(**(req.interview_config or {}))  # type: ignore
        submission_id = submission.id
        answers = dict(submission.answers or {})
        field_hints = dict(template.field_hints or {})  # type: ignore
        interview_type = req.interview_type  # type: ignore
        max_duration = cfg.max_duration_seconds
        difficulty_band = cfg.difficulty_band

    # Wait for resume parse + source enrichment (outside the session, no held tx).
    await _wait_for_inputs(SessionLocal, submission_id)

    # Attempt LLM plan (retry once on validation failure), else fallback.
    status = "ready"
    nodes: list[dict] | None = None
    async with SessionLocal() as db:
        submission = await db.get(FormSubmission, submission_id)  # type: ignore
        resume_md = submission.resume_markdown
        sources_digest = _sources_digest((submission.enrichment or {}).get("sources") or [])
    for attempt in range(2):
        try:
            nodes = await _llm_plan(
                interview_type,
                criteria,
                answers,
                field_hints,
                resume_md,
                sources_digest,
                max_duration,
                difficulty_band,
            )
            validate_plan(
                nodes,
                rubric_criteria_keys=set(criteria_keys),
                max_duration_seconds=max_duration,
                difficulty_band=difficulty_band,
            )
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("plan_attempt_failed", attempt=attempt, error=str(exc))
            nodes = None

    if nodes is None:
        nodes = load_fallback(interview_type)
        assign_criteria_round_robin(nodes, criteria_keys)
        status = "fallback_generic"

    total_budget = sum(int(n["soft_budget_seconds"]) for n in nodes)
    async with SessionLocal() as db:
        await write_plan(
            db,
            interview_id=interview_id,  # type: ignore
            nodes=nodes,
            status=status,
            model=settings.plan_llm,
            prompt_version=version_tag("plan"),
            total_budget_seconds=total_budget,
        )
        app = await db.get(Application, interview.application_id)
        if app.state == "form_submitted":  # type: ignore
            await apps.transition(db, app.id, "plan_ready", "system", {"plan_status": status})  # type: ignore

        # Cache the FULL interview context bundle (form + resume + scraped
        # sources + requisition + seed questions) for fast room-load reads.
        req = await db.get(Requisition, interview.requisition_id)  # type: ignore
        submission = await db.get(FormSubmission, submission_id)  # type: ignore
        bundle = assemble_context(
            req=req,
            submission=submission,
            field_hints=field_hints,
            plan_nodes=nodes,
            status="ready",
        )
        await cache_context(interview_id, bundle)
        await db.commit()


def _sources_digest(sources: list[dict]) -> list[dict]:
    """Compact view of scraped sources for the plan prompt — drop failed ones and
    heavy raw text, keep the LLM digest / GitHub structure / a short excerpt."""
    out: list[dict] = []
    for s in sources:
        if s.get("status") != "done":
            continue
        item: dict = {"kind": s.get("kind"), "url": s.get("url")}
        if s.get("digest"):
            item["digest"] = s["digest"]
        elif s.get("github"):
            item["github"] = s["github"]
        elif s.get("text"):
            item["text"] = s["text"][:1500]
        out.append(item)
    return out


async def _llm_plan(
    interview_type,
    criteria,
    answers,
    field_hints,
    resume_md,
    sources_digest,
    max_duration,
    difficulty_band,
) -> list[dict]:
    rubric_digest = [
        {"key": c.key, "name": c.name, "description": c.description, "weight": float(c.weight)}
        for c in criteria
    ]
    form_digest = {
        k: {"role": field_hints.get(k, {}).get("role"), "value": v}
        for k, v in answers.items()
        if field_hints.get(k, {}).get("use_in_plan")
    }
    prompt = (
        load_prompt("plan", "v1")
        .replace("{max_minutes}", str(max_duration // 60))
        .replace("{interview_type}", interview_type)
        .replace("{rubric_digest}", str(rubric_digest))
        .replace("{form_digest}", str(form_digest))
        .replace("{resume_md}", resume_md or "")
        .replace("{sources_json}", str(sources_digest))
        .replace("{difficulty_band}", str(difficulty_band))
        .replace("{budget_ceiling}", str(max_duration - 120))
    )
    agent = plan_generator()
    result = await agent.run(prompt)
    out = getattr(result, "output", None) or getattr(result, "data", None)
    return [n.model_dump() for n in out.nodes]  # type: ignore
