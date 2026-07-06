"""finalize_interview + scoring orchestration jobs (SPEC §11, §14).

finalize_interview is implemented (closes nodes, renumbers, marks finalized,
enqueues scoring + identity).  The direct sequential scoring pipeline
(run_scoring → aggregate_scores → build_report) is Phase-3 work implemented
here.

TODO(spec-deviation): move to provider Batch API (D15) for the 50% discount.
Currently we run LLM calls sequentially (one per criterion × run_index) so the
chain produces correct results without a batch-polling loop.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.queue import enqueue
from app.db.models import (
    Application,
    CriterionScore,
    Evaluation,
    EvidenceNote,
    IdentityCheck,
    Interview,
    ProctoringEvent,
    QuestionPlan,
    QuestionPlanNode,
    Report,
    Requisition,
    Rubric,
    RubricCriterion,
    ScoringJob,
    Turn,
)
from app.db.session import SessionLocal
from app.domain import applications as apps
from app.domain.evidence import EvidencePacket, build_evidence_packet
from app.domain.scoring import RunScore, aggregate_runs, anchor_to_score100, filter_evidence
from app.llm.clients import ensure_provider_env, report_writer
from app.llm.prompts import load_prompt, version_tag
from app.llm.schemas import CriterionScoreOut, ReportDraft
from app.schemas.interview_config import InterviewConfig

log = structlog.get_logger(__name__)

_MIN_TURNS_TO_SCORE = 3  # SPEC §11.1


# ---------------------------------------------------------------------------
# Public helpers (pure, extracted for testing)
# ---------------------------------------------------------------------------


def _fill_score_prompt(raw_template: str, packet: EvidencePacket) -> str:
    """Fill the score_v1.md template with per-criterion packet data."""
    c = packet.criterion
    return (
        raw_template.replace("{name}", c.get("name", ""))
        .replace("{description}", c.get("description", ""))
        .replace("{anchors}", str(c.get("level_anchors", [])))
        .replace("{slice}", json.dumps(packet.transcript_slice, ensure_ascii=False))
        .replace("{notes}", json.dumps(packet.notes, ensure_ascii=False))
        .replace("{coverage_note}", packet.coverage_note or "full coverage")
    )


def _fill_report_prompt(
    raw_template: str,
    evaluations_data: list[dict],
    coverage: list[dict],
    proctoring_summary: dict,
    meta: dict,
) -> str:
    """Fill the report_v1.md template with structured result data."""
    return (
        raw_template.replace("{evaluations}", json.dumps(evaluations_data, ensure_ascii=False))
        .replace("{coverage}", json.dumps(coverage, ensure_ascii=False))
        .replace("{proctoring}", json.dumps(proctoring_summary, ensure_ascii=False))
        .replace("{meta}", json.dumps(meta, ensure_ascii=False))
    )


def _fallback_report_draft(
    evaluations_data: list[dict],
    overall_score: float,
    end_reason: str | None = None,
) -> ReportDraft:
    """Deterministic report when the report LLM fails (SPEC §11.5 fallback)."""
    prefix = ""
    if end_reason == "abandoned":
        prefix = "Note: interview was not completed; coverage is partial. "

    scored = [ev for ev in evaluations_data if ev.get("final_score") is not None]
    by_score = sorted(scored, key=lambda e: e["final_score"], reverse=True)
    summary = (
        f"{prefix}Overall score: {overall_score:.2f}. "
        f"Evaluated {len(scored)} criterion/criteria. "
        "Report generated without LLM assistance."
    )
    strengths = [
        f"{e['criterion_key']}: score {e['final_score']:.0f}"
        for e in by_score
        if e["final_score"] >= 75.0
    ]
    concerns = [
        f"{e['criterion_key']}: score {e['final_score']:.0f}"
        for e in by_score
        if e["final_score"] <= 25.0
    ]
    return ReportDraft(summary=summary, strengths=strengths, concerns=concerns)


def _compute_overall_score(evaluations: list[dict], weights: dict[str, float]) -> float:
    """Weighted average: Σ(final_score × weight) / 100, rounded to 2dp.

    Criteria not present in weights are skipped (should not happen in practice).
    """
    total = 0.0
    for ev in evaluations:
        key = ev["criterion_key"]
        score = float(ev["final_score"])
        weight = float(weights.get(key, 0.0))
        total += score * weight
    return round(total / 100.0, 2)


# ---------------------------------------------------------------------------
# finalize_interview (already implemented)
# ---------------------------------------------------------------------------


async def finalize_interview(ctx: dict, interview_id: str) -> None:
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None or interview.status == "finalized":
            return  # idempotent

        plan = (
            await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview.id))
        ).scalar_one_or_none()
        if plan is not None:
            nodes = (
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
            # Close open nodes; renumber positions to integers (SPEC §11.1).
            for position, n in enumerate(nodes):
                if n.state in ("pending", "active"):
                    n.state = "skipped"
                    n.skip_reason = n.skip_reason or "time_exhausted"
                n.position = position

        if interview.status == "ended":
            interview.status = "finalized"

        candidate_turns = (
            await db.execute(
                select(func.count(Turn.id)).where(
                    Turn.interview_id == interview.id, Turn.speaker == "candidate"
                )
            )
        ).scalar_one()

        req = await db.get(Requisition, interview.requisition_id)
        cfg = InterviewConfig(**(req.interview_config or {}))  # type: ignore
        await db.commit()

    if candidate_turns >= _MIN_TURNS_TO_SCORE:
        await enqueue("run_scoring", interview_id)
    else:
        log.info(
            "scoring_skipped_insufficient_data",
            interview_id=interview_id,
            candidate_turns=candidate_turns,
        )

    if cfg.proctoring.identity_check:
        await enqueue("identity_check", interview_id)


# ---------------------------------------------------------------------------
# run_scoring — direct sequential path (Phase-3)
# ---------------------------------------------------------------------------


async def run_scoring(ctx: dict, interview_id: str) -> None:
    """Score all rubric criteria for a finalized interview (SPEC §11.3).

    Direct sequential path — one LLM call per criterion × run_index.
    TODO(spec-deviation): move to provider Batch API (D15) for the 50% discount.
    """
    # --- 1. Idempotency: find or create scoring_jobs row ------------------
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(ScoringJob).where(ScoringJob.interview_id == interview_id))
        ).scalar_one_or_none()

        if existing is not None:
            if existing.status == "done":
                log.info("run_scoring_already_done", interview_id=interview_id)
                return
            if existing.status == "aggregating":
                log.info("run_scoring_resuming_aggregating", interview_id=interview_id)
                job_id = str(existing.id)
                await db.commit()
                await aggregate_scores(ctx, job_id)
                return
            # status is 'queued' or 'failed' — (re)try
            if existing.status == "failed":
                existing.status = "queued"
                existing.error = None
            job = existing
        else:
            job = ScoringJob(
                id=new_id(),
                interview_id=interview_id,
                status="queued",
                runs_requested=settings.scoring_runs,
                model=settings.score_llm,
                prompt_version=version_tag("score"),
            )
            db.add(job)

        await db.commit()
        job_id = str(job.id)

    log.info("run_scoring_start", interview_id=interview_id, job_id=job_id)

    # --- 2. Check provider environment ------------------------------------
    try:
        ensure_provider_env()
    except AppError as exc:
        log.error("run_scoring_no_provider", interview_id=interview_id, error=exc.message)
        async with SessionLocal() as db:
            sj = await db.get(ScoringJob, job.id)
            if sj is not None:
                sj.status = "failed"
                sj.error = exc.message
                await db.commit()
        return

    # --- 3. Load interview data -------------------------------------------
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            log.error("run_scoring_interview_missing", interview_id=interview_id)
            return

        req = await db.get(Requisition, interview.requisition_id)
        rubric = await db.get(Rubric, req.rubric_id)  # type: ignore

        criteria_rows = (
            (
                await db.execute(
                    select(RubricCriterion)
                    .where(RubricCriterion.rubric_id == rubric.id)  # type: ignore
                    .order_by(RubricCriterion.display_order)
                )
            )
            .scalars()
            .all()
        )

        turns_rows = (
            (
                await db.execute(
                    select(Turn).where(Turn.interview_id == interview.id).order_by(Turn.seq)
                )
            )
            .scalars()
            .all()
        )

        plan_row = (
            await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview.id))
        ).scalar_one_or_none()

        nodes_rows: list = []
        if plan_row is not None:
            nodes_rows = (
                (  # type: ignore
                    await db.execute(
                        select(QuestionPlanNode).where(QuestionPlanNode.plan_id == plan_row.id)
                    )
                )
                .scalars()
                .all()
            )

        evidence_note_rows = (
            (
                await db.execute(
                    select(EvidenceNote).where(EvidenceNote.interview_id == interview.id)
                )
            )
            .scalars()
            .all()
        )

    # Convert ORM rows to plain dicts for the pure evidence module.
    criteria = [
        {
            "key": c.key,
            "name": c.name,
            "description": c.description,
            "weight": float(c.weight),
            "level_anchors": list(c.level_anchors or []),
        }
        for c in criteria_rows
    ]

    all_turns = [
        {
            "id": str(t.id),
            "seq": t.seq,
            "speaker": t.speaker,
            "text": t.text,
            "node_id": str(t.node_id) if t.node_id else None,
        }
        for t in turns_rows
    ]

    node_target_criteria: dict[str, list[str]] = {
        str(n.id): list(n.target_criteria or []) for n in nodes_rows
    }

    evidence_notes = [
        {
            "id": str(n.id),
            "turn_id": str(n.turn_id),
            "criterion_key": n.criterion_key,
            "signal": n.signal,
            "note": n.note,
        }
        for n in evidence_note_rows
    ]

    raw_score_template = load_prompt("score", "v1")

    # --- 4. Score each criterion × run_index -----------------------------
    from pydantic_ai import Agent
    from pydantic_ai.settings import ModelSettings

    score_model_settings = ModelSettings(temperature=0.4)

    for criterion in criteria:
        packet = build_evidence_packet(
            criterion=criterion,
            all_turns=all_turns,
            node_target_criteria=node_target_criteria,
            evidence_notes=evidence_notes,
        )
        filled_prompt = _fill_score_prompt(raw_score_template, packet)

        for run_index in range(settings.scoring_runs):
            # Idempotency: skip if this run already has a score.
            async with SessionLocal() as db:
                already = (
                    await db.execute(
                        select(CriterionScore).where(
                            CriterionScore.scoring_job_id == job.id,
                            CriterionScore.run_index == run_index,
                            CriterionScore.criterion_key == criterion["key"],
                        )
                    )
                ).scalar_one_or_none()
            if already is not None:
                continue

            # Try to score — retry once on failure, then skip.
            score_out: CriterionScoreOut | None = None
            for attempt in range(2):
                try:
                    agent = Agent(
                        settings.score_llm,
                        output_type=CriterionScoreOut,
                        defer_model_check=True,
                    )
                    result = await agent.run(filled_prompt, model_settings=score_model_settings)
                    score_out = getattr(result, "output", None) or getattr(result, "data", None)
                    break
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "score_call_failed",
                        interview_id=interview_id,
                        criterion_key=criterion["key"],
                        run_index=run_index,
                        attempt=attempt,
                        error=str(exc),
                    )
                    score_out = None

            if score_out is None:
                log.warning(
                    "score_run_skipped",
                    criterion_key=criterion["key"],
                    run_index=run_index,
                )
                continue

            # Persist the criterion_score row.
            async with SessionLocal() as db:
                db.add(
                    CriterionScore(
                        id=new_id(),
                        scoring_job_id=job.id,
                        run_index=run_index,
                        criterion_key=criterion["key"],
                        score=score_out.score,
                        confidence=score_out.confidence,
                        evidence=[e.model_dump() for e in score_out.evidence],
                        rationale=score_out.rationale,
                    )
                )
                await db.commit()

            log.info(
                "score_run_saved",
                criterion_key=criterion["key"],
                run_index=run_index,
                score=score_out.score,
            )

    # --- 5. Advance to aggregation ----------------------------------------
    async with SessionLocal() as db:
        sj = await db.get(ScoringJob, job.id)
        if sj is not None and sj.status not in ("done", "failed"):
            sj.status = "aggregating"
            await db.commit()

    await aggregate_scores(ctx, job_id)


# ---------------------------------------------------------------------------
# aggregate_scores
# ---------------------------------------------------------------------------


async def aggregate_scores(ctx: dict, scoring_job_id: str) -> None:
    """Median aggregation + quote verification → evaluations rows (SPEC §11.4)."""
    import uuid

    async with SessionLocal() as db:
        sj = await db.get(ScoringJob, uuid.UUID(scoring_job_id))
        if sj is None:
            log.error("aggregate_scores_job_missing", scoring_job_id=scoring_job_id)
            return

        interview_id = str(sj.interview_id)

        # Load all criterion_scores for this job.
        score_rows = (
            (await db.execute(select(CriterionScore).where(CriterionScore.scoring_job_id == sj.id)))
            .scalars()
            .all()
        )

        # Load rubric criteria (for weights and keys).
        interview = await db.get(Interview, sj.interview_id)
        req = await db.get(Requisition, interview.requisition_id)  # type: ignore
        rubric = await db.get(Rubric, req.rubric_id)  # type: ignore
        criteria_rows = (
            (
                await db.execute(
                    select(RubricCriterion)
                    .where(RubricCriterion.rubric_id == rubric.id)  # type: ignore
                    .order_by(RubricCriterion.display_order)
                )
            )
            .scalars()
            .all()
        )

        # Turn text for quote verification.
        turns_rows = (
            (await db.execute(select(Turn).where(Turn.interview_id == sj.interview_id)))
            .scalars()
            .all()
        )

        # Evidence notes (for coverage_gap detection).
        evidence_note_rows = (
            (
                await db.execute(
                    select(EvidenceNote).where(EvidenceNote.interview_id == sj.interview_id)
                )
            )
            .scalars()
            .all()
        )

        # Plan nodes (for coverage_gap detection).
        plan_row = (
            await db.execute(
                select(QuestionPlan).where(QuestionPlan.interview_id == sj.interview_id)
            )
        ).scalar_one_or_none()
        nodes_rows: list = []
        if plan_row is not None:
            nodes_rows = (
                (  # type: ignore
                    await db.execute(
                        select(QuestionPlanNode).where(QuestionPlanNode.plan_id == plan_row.id)
                    )
                )
                .scalars()
                .all()
            )

    # Build look-ups.
    turn_text_by_id: dict[str, str] = {str(t.id): t.text for t in turns_rows}
    node_target_criteria: dict[str, list[str]] = {
        str(n.id): list(n.target_criteria or []) for n in nodes_rows
    }
    all_turns_plain = [
        {
            "id": str(t.id),
            "seq": t.seq,
            "speaker": t.speaker,
            "text": t.text,
            "node_id": str(t.node_id) if t.node_id else None,
        }
        for t in turns_rows
    ]
    evidence_notes_plain = [
        {
            "id": str(n.id),
            "turn_id": str(n.turn_id),
            "criterion_key": n.criterion_key,
            "signal": n.signal,
            "note": n.note,
        }
        for n in evidence_note_rows
    ]

    # Group criterion_score rows by criterion key.
    scores_by_criterion: dict[str, list[CriterionScore]] = {}
    for row in score_rows:
        scores_by_criterion.setdefault(row.criterion_key, []).append(row)

    evaluations_data: list[dict] = []
    weights: dict[str, float] = {c.key: float(c.weight) for c in criteria_rows}

    async with SessionLocal() as db:
        for criterion in criteria_rows:
            ckey = criterion.key

            # Detect coverage gap (same logic as evidence assembly).
            packet = build_evidence_packet(
                criterion={
                    "key": criterion.key,
                    "name": criterion.name,
                    "description": criterion.description,
                    "weight": float(criterion.weight),
                    "level_anchors": list(criterion.level_anchors or []),
                },
                all_turns=all_turns_plain,
                node_target_criteria=node_target_criteria,
                evidence_notes=evidence_notes_plain,
            )
            coverage_gap = packet.coverage_note == "no targeted turns"

            raw_runs = scores_by_criterion.get(ckey, [])

            if not raw_runs:
                # Zero scores for this criterion — write a fallback evaluation.
                log.warning("aggregate_zero_runs", criterion_key=ckey, interview_id=interview_id)
                ev = Evaluation(
                    id=new_id(),
                    interview_id=sj.interview_id,
                    criterion_key=ckey,
                    final_score=0.0,
                    method="median",
                    disagreement=False,
                    needs_review=True,
                    evidence=[],
                    rationale="scoring failed",
                )
                db.add(ev)
                evaluations_data.append(
                    {
                        "criterion_key": ckey,
                        "final_score": 0.0,
                        "needs_review": True,
                        "rationale": "scoring failed",
                        "evidence": [],
                    }
                )
                continue

            # Convert to RunScore dataclass and apply quote verification.
            run_scores = [
                RunScore(
                    run_index=row.run_index,
                    score=row.score,
                    confidence=float(row.confidence or 0.0),
                    evidence=list(row.evidence or []),
                    rationale=row.rationale,
                )
                for row in raw_runs
            ]
            for rs in run_scores:
                filter_evidence(rs, turn_text_by_id)

            agg = aggregate_runs(run_scores, coverage_gap=coverage_gap)
            # Aggregation stays anchor-space (disagreement math is 1–5 native);
            # persist and report on the 0–100 scale.
            final_score100 = anchor_to_score100(agg.final_score)

            ev = Evaluation(
                id=new_id(),
                interview_id=sj.interview_id,
                criterion_key=ckey,
                final_score=final_score100,
                method=agg.method,
                disagreement=agg.disagreement,
                needs_review=agg.needs_review,
                evidence=agg.evidence,
                rationale=agg.rationale,
            )
            db.add(ev)
            evaluations_data.append(
                {
                    "criterion_key": ckey,
                    "final_score": final_score100,
                    "disagreement": agg.disagreement,
                    "needs_review": agg.needs_review,
                    "rationale": agg.rationale,
                    "evidence": agg.evidence,
                }
            )

        await db.commit()

    overall_score = _compute_overall_score(evaluations_data, weights)
    log.info(
        "aggregate_scores_done",
        interview_id=interview_id,
        overall_score=overall_score,
        criteria_count=len(evaluations_data),
    )

    await build_report(ctx, interview_id, evaluations_data, overall_score, nodes_rows)


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------


async def build_report(
    ctx: dict,
    interview_id: str,
    evaluations_data: list[dict] | None = None,
    overall_score: float | None = None,
    nodes_rows: list | None = None,
) -> None:
    """Write a reports row from structured results only (SPEC §11.5)."""
    import uuid

    async with SessionLocal() as db:
        interview = await db.get(Interview, uuid.UUID(interview_id))
        if interview is None:
            log.error("build_report_interview_missing", interview_id=interview_id)
            return

        # Load evaluations if not passed in (direct-call path re-loads them).
        if evaluations_data is None:
            eval_rows = (
                (
                    await db.execute(
                        select(Evaluation).where(Evaluation.interview_id == interview.id)
                    )
                )
                .scalars()
                .all()
            )
            evaluations_data = [
                {
                    "criterion_key": e.criterion_key,
                    "final_score": float(e.final_score),
                    "needs_review": e.needs_review,
                    "rationale": e.rationale,
                    "evidence": list(e.evidence or []),
                }
                for e in eval_rows
            ]

        # Recompute overall_score if not provided.
        if overall_score is None:
            req = await db.get(Requisition, interview.requisition_id)
            rubric = await db.get(Rubric, req.rubric_id)  # type: ignore
            criteria_rows = (
                (
                    await db.execute(
                        select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id)  # type: ignore
                    )
                )
                .scalars()
                .all()
            )
            weights = {c.key: float(c.weight) for c in criteria_rows}
            overall_score = _compute_overall_score(evaluations_data, weights)

        # Coverage node list.
        if nodes_rows is None:
            plan_row = (
                await db.execute(
                    select(QuestionPlan).where(QuestionPlan.interview_id == interview.id)
                )
            ).scalar_one_or_none()
            if plan_row is not None:
                nodes_rows = (
                    (  # type: ignore
                        await db.execute(
                            select(QuestionPlanNode)
                            .where(QuestionPlanNode.plan_id == plan_row.id)
                            .order_by(QuestionPlanNode.position)
                        )
                    )
                    .scalars()
                    .all()
                )
            else:
                nodes_rows = []

        coverage = [
            {
                "node_id": str(n.id),
                "title": n.title,
                "state": n.state,
                "skip_reason": n.skip_reason,
            }
            for n in nodes_rows  # type: ignore
        ]

        # Proctoring summary.
        proctoring_counts = (
            await db.execute(
                select(ProctoringEvent.type, func.count())
                .where(ProctoringEvent.interview_id == interview.id)
                .group_by(ProctoringEvent.type)
            )
        ).all()
        proctoring_summary: dict = {row[0]: row[1] for row in proctoring_counts}

        identity = (
            await db.execute(
                select(IdentityCheck).where(IdentityCheck.interview_id == interview.id)
            )
        ).scalar_one_or_none()
        if identity is not None and identity.verdict:
            proctoring_summary["identity_verdict"] = identity.verdict

        # Interview meta.
        meta = {
            "duration_seconds": interview.elapsed_active_seconds,
            "end_reason": interview.end_reason or "unknown",
        }

        app_id = interview.application_id

    # --- LLM report generation (with deterministic fallback) --------------
    filled_report_prompt = _fill_report_prompt(
        load_prompt("report", "v1"),
        evaluations_data,
        coverage,
        proctoring_summary,
        meta,
    )

    draft: ReportDraft | None = None
    try:
        ensure_provider_env()
        agent = report_writer()
        result = await agent.run(filled_report_prompt)
        draft = getattr(result, "output", None) or getattr(result, "data", None)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "report_llm_failed",
            interview_id=interview_id,
            error=str(exc),
        )
        draft = None

    if draft is None:
        draft = _fallback_report_draft(evaluations_data, overall_score, interview.end_reason)

    # Prepend abandoned caveat (SPEC §11.1/E5).
    summary = draft.summary
    if interview.end_reason == "abandoned" and not summary.startswith(
        "Note: interview was not completed"
    ):
        summary = "Note: interview was not completed; coverage is partial. " + summary

    # --- Persist report row and finalize ----------------------------------
    async with SessionLocal() as db:
        db.add(
            Report(
                id=new_id(),
                interview_id=uuid.UUID(interview_id),
                overall_score=overall_score,
                summary=summary,
                strengths=list(draft.strengths),
                concerns=list(draft.concerns),
                coverage=coverage,
                proctoring_summary=proctoring_summary,
                status="draft",
                html_file_id=None,
            )
        )

        # Mark scoring job done.
        sj_obj = (
            await db.execute(
                select(ScoringJob).where(ScoringJob.interview_id == uuid.UUID(interview_id))
            )
        ).scalar_one_or_none()
        if sj_obj is not None:
            sj_obj.status = "done"
            sj_obj.completed_at = datetime.now(UTC)

        # Transition application completed → scored (SPEC §11.5).
        app = await db.get(Application, app_id)
        if app is not None and app.state == "completed":
            try:
                await apps.transition(db, app.id, "scored", "system")
                log.info("application_transitioned_scored", application_id=str(app.id))
            except AppError as exc:
                log.warning(
                    "app_transition_skipped",
                    application_id=str(app.id),
                    reason=exc.message,
                )

        await db.commit()

    log.info(
        "build_report_done",
        interview_id=interview_id,
        overall_score=overall_score,
    )


# ---------------------------------------------------------------------------
# Remaining arq stubs
# ---------------------------------------------------------------------------


async def poll_batches(ctx: dict) -> None:
    """Cron (60s): poll submitted/polling scoring jobs, ingest criterion_scores,
    trigger aggregate_scores. TODO(Phase-3): provider Batch API poll shapes."""
    return


async def identity_check(ctx: dict, interview_id: str) -> None:
    """InsightFace identity check (SPEC §10.5). TODO(Phase-4)."""
    return


async def refresh_summary(ctx: dict, interview_id: str) -> None:
    """Rolling transcript summary → Redis summary:{interview_id} (SPEC §14). TODO(Phase-2)."""
    return
