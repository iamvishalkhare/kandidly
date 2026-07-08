"""Dev seed data (SPEC §18.4). Idempotent: safe to run repeatedly.

Creates: the default organization's staff + candidate users (display names
match the console mock roster); catalog autocomplete entries; the published
swe_backend KYI template + rubric; six requisitions across domains (flagship
ENG-001 plus five others, each with its own published template/rubric and
invite link); and six completed interview pipelines on the flagship —
applications, form submissions, consents, finalized interviews, question
plans, transcripts, criterion scores (1–5 anchors), evaluations (0–100),
reports (some reviewed), proctoring events/snapshots, and audit rows.

When MinIO is reachable it also uploads a generated WAV recording per
interview (referenced via interviews.audio_recording_id, with precomputed
peaks in interviews.audio_waveform) and placeholder proctor snapshots;
otherwise those media rows are skipped with a warning.

Requires migrations at head (the default org row is created by 0003).

Run:  python -m app.db.seed
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import wave
from datetime import UTC, datetime, timedelta
from statistics import median
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy import text as sa_text

from app.core import storage
from app.core.config import settings
from app.core.ids import new_id
from app.db import seed_fixtures as fx
from app.db.base import Base
from app.db.models import (
    Application,
    ApplicationEvent,
    AuditLog,
    CatalogEntry,
    Consent,
    CriterionScore,
    Evaluation,
    FormSubmission,
    FormTemplate,
    Interview,
    InviteLink,
    Organization,
    ProctoringEvent,
    ProctoringSnapshot,
    QuestionPlan,
    QuestionPlanNode,
    Report,
    Requisition,
    Rubric,
    RubricCriterion,
    ScoringJob,
    StoredFile,
    Turn,
    User,
)
from app.db.session import SessionLocal
from app.domain.builder import builder_fields_to_schema, builder_rubric_to_criteria
from app.domain.links import generate_token
from app.domain.scoring import anchor_to_score100
from app.schemas.interview_config import InterviewConfig

TEMPLATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "x-kandidly": {
        "profile": "kyi-form/v1",
        "field_order": [
            "full_name",
            "current_role",
            "years_python",
            "kafka_rating",
            "domains",
            "complex_system",
            "open_source",
            "earliest_start",
            "github",
            "resume",
        ],
    },
    "required": ["full_name", "resume"],
    "properties": {
        "full_name": {
            "type": "string",
            "title": "Full name",
            "maxLength": 120,
            "x-field": "short_text",
            "x-builder-type": "text",
        },
        "current_role": {
            "type": "string",
            "title": "Current role / title",
            "maxLength": 120,
            "x-field": "short_text",
            "x-builder-type": "text",
        },
        "years_python": {
            "type": "integer",
            "title": "Years of Python experience",
            "minimum": 0,
            "maximum": 40,
            "x-field": "number",
            "x-builder-type": "text",
        },
        "kafka_rating": {
            "type": "integer",
            "title": "Rate your Kafka proficiency",
            "minimum": 1,
            "maximum": 5,
            "x-field": "scale",
            "x-builder-type": "range",
        },
        "domains": {
            "type": "array",
            "title": "Domains you have worked in",
            "items": {"enum": ["payments", "healthcare", "ecommerce", "other"]},
            "x-field": "multi_select",
            "x-builder-type": "multi_select",
        },
        "complex_system": {
            "type": "string",
            "title": "Describe the most complex system you built",
            "maxLength": 2000,
            "x-field": "long_text",
            "x-builder-type": "textarea",
        },
        "open_source": {
            "type": "string",
            "title": "Do you contribute to open source?",
            "enum": ["Yes", "No"],
            "x-field": "single_select",
            "x-builder-type": "multiple_choice",
        },
        "earliest_start": {
            "type": "string",
            "title": "Earliest available start date",
            "maxLength": 40,
            "x-field": "short_text",
            "x-builder-type": "date",
            "x-placeholder": "YYYY-MM-DD",
        },
        "github": {
            "type": "string",
            "title": "Link your GitHub profile",
            "maxLength": 300,
            "x-field": "short_text",
            "x-builder-type": "social",
            "x-placeholder": "https://github.com/…",
        },
        "resume": {
            "type": "string",
            "title": "Upload your resume",
            "x-field": "file",
            "x-builder-type": "file",
            "x-accept": [".pdf", ".docx"],
            "x-max-bytes": 10485760,
        },
    },
}

FIELD_HINTS = {
    "kafka_rating": {
        "use_in_plan": True,
        "role": "difficulty_signal",
        "maps_to_criteria": ["distributed_systems"],
    },
    "complex_system": {
        "use_in_plan": True,
        "role": "seed_topic",
        "maps_to_criteria": ["system_design_depth", "ownership"],
    },
    "domains": {"use_in_plan": True, "role": "context"},
    "years_python": {"use_in_plan": True, "role": "difficulty_signal"},
    "full_name": {"use_in_plan": False},
}


def _anchors(a1, a2, a3, a4, a5):
    return [
        {"level": 1, "anchor": a1},
        {"level": 2, "anchor": a2},
        {"level": 3, "anchor": a3},
        {"level": 4, "anchor": a4},
        {"level": 5, "anchor": a5},
    ]


RUBRIC_CRITERIA = [
    (
        "system_design_depth",
        "System design depth",
        "Depth and soundness of architectural reasoning.",
        30,
        1,
        _anchors(
            "No structure.",
            "Names components only.",
            "Reasonable design, few tradeoffs.",
            "Solid design with explicit tradeoffs.",
            "Excellent; anticipates failure modes.",
        ),
    ),
    (
        "distributed_systems",
        "Distributed systems",
        "Consistency, failure handling, scaling.",
        25,
        2,
        _anchors(
            "No awareness.",
            "Buzzwords only.",
            "Basic correct notions.",
            "Concrete mechanisms explained.",
            "Deep, example-grounded mastery.",
        ),
    ),
    (
        "ownership",
        "Ownership & scope",
        "Personal responsibility and end-to-end ownership.",
        20,
        3,
        _anchors(
            "Peripheral role.",
            "Contributed small parts.",
            "Owned a component.",
            "Owned a system end-to-end.",
            "Drove org-level outcomes.",
        ),
    ),
    (
        "problem_solving",
        "Problem solving",
        "Debugging rigor and structured reasoning.",
        15,
        4,
        _anchors(
            "Gives up.",
            "Trial and error.",
            "Systematic approach.",
            "Strong hypothesis-driven debugging.",
            "Exceptional first-principles reasoning.",
        ),
    ),
    (
        "communication",
        "Communication",
        "Clarity and structure of spoken explanation.",
        10,
        5,
        _anchors(
            "Incoherent.",
            "Hard to follow.",
            "Clear enough.",
            "Clear and well-structured.",
            "Crisp, precise, audience-aware.",
        ),
    ),
]

FLAGSHIP_CODE = "ENG-001"
FLAGSHIP_TITLE = "Backend Engineer (Seed)"
WEIGHTS = {key: float(weight) for key, _, _, weight, _, _ in RUBRIC_CRITERIA}

# Minimal valid 1×1 lossless WebP for placeholder proctor snapshots.
WEBP_1PX = base64.b64decode("UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA==")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _stable_user_id(email: str) -> UUID:
    """Deterministic id for a seed account, derived from its email. Keeps the
    well-known dev users' ids (and thus their /dev-users bearer tokens) stable
    across `--reset` re-seeds, so re-seeding does not silently invalidate a
    token already stored in a browser's localStorage."""
    return uuid5(NAMESPACE_URL, f"kandidly-seed-user:{email.lower()}")


async def _get_or_create_user(
    db, email: str, role: str, *, display_name: str | None = None, org_id=None
) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        if display_name and existing.display_name is None:
            existing.display_name = display_name
        if org_id is not None and existing.org_id is None and role != "candidate":
            existing.org_id = org_id
        return existing
    user = User(
        id=_stable_user_id(email),
        email=email,
        role=role,
        display_name=display_name,
        org_id=org_id if role != "candidate" else None,
    )
    db.add(user)
    await db.flush()
    return user


def _dev_token(user: User) -> str:
    payload = {"user_id": str(user.id), "email": user.email, "role": user.role}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def _gen_wav(variant: int, seconds: int = 30) -> tuple[bytes, list[int]]:
    """Deterministic sine-sweep speech-ish WAV (16 kHz mono 16-bit) plus
    1024-bin 0–100 peaks for the review player."""
    sr = 16000
    n = sr * seconds
    samples = bytearray()
    values: list[float] = []
    for i in range(n):
        t = i / sr
        # Alternate "speech bursts" and pauses; vary pitch per interview.
        burst = math.sin(2 * math.pi * (0.22 + 0.03 * variant) * t)
        envelope = max(0.0, burst) ** 2
        freq = 140 + 40 * variant + 60 * math.sin(2 * math.pi * 0.5 * t)
        v = envelope * 0.7 * math.sin(2 * math.pi * freq * t)
        values.append(v)
        iv = int(v * 32767)
        samples += iv.to_bytes(2, "little", signed=True)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(samples))
    bins = 1024
    per = max(1, n // bins)
    peaks = [
        min(100, int(max(abs(v) for v in values[k * per : (k + 1) * per] or [0.0]) * 100))
        for k in range(bins)
    ]
    return buf.getvalue(), peaks


async def _probe_s3() -> bool:
    try:
        await storage.put_object(storage.BUCKET_SNAPSHOTS, "seed/probe.txt", b"ok", "text/plain")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: S3/MinIO unreachable ({exc}); skipping media uploads.")
        return False


async def _ensure_org(db) -> Organization:
    org = (
        await db.execute(select(Organization).where(Organization.slug == settings.default_org_slug))
    ).scalar_one_or_none()
    if org is None:
        raise RuntimeError(
            f"Default organization '{settings.default_org_slug}' missing — "
            "run `alembic upgrade head` before seeding."
        )
    return org


async def _ensure_catalog(db, org_id, admin_id) -> None:
    for kind, values in fx.CATALOG.items():
        existing = set(
            (
                await db.execute(
                    select(CatalogEntry.value).where(
                        CatalogEntry.org_id == org_id, CatalogEntry.kind == kind
                    )
                )
            )
            .scalars()
            .all()
        )
        for value in values:
            if value not in existing:
                db.add(
                    CatalogEntry(
                        id=new_id(), org_id=org_id, kind=kind, value=value, created_by=admin_id
                    )
                )


async def _create_template(db, org_id, admin_id, *, interview_type, title, schema, hints, now):
    t = FormTemplate(
        id=new_id(),
        org_id=org_id,
        family_id=new_id(),
        version=1,
        interview_type=interview_type,
        title=title,
        schema=schema,
        field_hints=hints,
        status="published",
        created_by=admin_id,
        published_at=now,
    )
    db.add(t)
    return t


async def _create_rubric(db, org_id, admin_id, *, interview_type, title, criteria, now):
    r = Rubric(
        id=new_id(),
        org_id=org_id,
        family_id=new_id(),
        version=1,
        interview_type=interview_type,
        title=title,
        status="published",
        created_by=admin_id,
        published_at=now,
    )
    db.add(r)
    await db.flush()
    for key, name, desc, weight, order, anchors in criteria:
        db.add(
            RubricCriterion(
                id=new_id(),
                rubric_id=r.id,
                key=key,
                name=name,
                description=desc,
                weight=weight,
                display_order=order,
                level_anchors=anchors,
            )
        )
    return r


def _rubric_rows_to_tuples(rows: list[dict]) -> list[tuple]:
    """Builder rubric rows ({name,description,weight}) → _create_rubric tuples,
    reusing the console's slug/anchor logic so keys and generic anchors match
    what the builder produces on deploy."""
    return [
        (c["key"], c["name"], c["description"], c["weight"], c["display_order"], c["level_anchors"])
        for c in builder_rubric_to_criteria(rows, is_draft=False)
    ]


async def _req_by_code(db, org_id, code: str) -> Requisition | None:
    return (
        await db.execute(
            select(Requisition).where(Requisition.org_id == org_id, Requisition.code == code)
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# requisitions
# --------------------------------------------------------------------------- #
async def _ensure_flagship(db, org, admin, now) -> tuple[Requisition, InviteLink]:
    req = await _req_by_code(db, org.id, FLAGSHIP_CODE)
    if req is None:
        # A pre-0003 seed may have created it with a backfilled REQ-#### code.
        req = (
            await db.execute(select(Requisition).where(Requisition.title == FLAGSHIP_TITLE))
        ).scalar_one_or_none()

    if req is None:
        template = await _create_template(
            db,
            org.id,
            admin.id,
            interview_type="swe_backend",
            title="Backend Engineer KYI",
            schema=TEMPLATE_SCHEMA,
            hints=FIELD_HINTS,
            now=now,
        )
        rubric = await _create_rubric(
            db,
            org.id,
            admin.id,
            interview_type="swe_backend",
            title="Backend Engineer Rubric",
            criteria=RUBRIC_CRITERIA,
            now=now,
        )
        await db.flush()
        req = Requisition(
            id=new_id(),
            org_id=org.id,
            code=FLAGSHIP_CODE,
            title=FLAGSHIP_TITLE,
            interview_type="swe_backend",
            form_template_id=template.id,
            rubric_id=rubric.id,
            status="open",
            interview_config=InterviewConfig(tone="technical").model_dump(),
            created_by=admin.id,
        )
        db.add(req)
        await db.flush()

    # Console fields (also upgrades rows created by older seeds).
    req.code = FLAGSHIP_CODE
    req.domain = "Engineering"
    req.technical_requirements = ["Python", "PostgreSQL", "Kafka", "Kubernetes"]
    req.role_objective = (
        "Own high-throughput backend services end-to-end: design, delivery, "
        "and operations. We want strong distributed-systems judgment and "
        "clear communication of tradeoffs."
    )
    req.sample_questions = [
        {"id": "sq-1", "text": "Tell me about the most complex system you have built."},
        {"id": "sq-2", "text": "How do you decide when a service boundary deserves to exist?"},
        {"id": "sq-3", "text": "Walk me through a production incident you personally root-caused."},
        {"id": "sq-4", "text": "How do you communicate consistency tradeoffs to product teams?"},
    ]
    # Seed the builder's "Close Date" with a concrete future datetime.
    req.end_date = (now + timedelta(days=45)).replace(hour=23, minute=59, second=0, microsecond=0)
    req.closes_at = req.end_date

    link = (
        await db.execute(
            select(InviteLink).where(InviteLink.requisition_id == req.id, InviteLink.kind == "open")
        )
    ).scalar_one_or_none()
    if link is None:
        link = InviteLink(
            id=new_id(),
            requisition_id=req.id,
            token=generate_token(),
            kind="open",
            created_by=admin.id,
        )
        db.add(link)
        await db.flush()
    if link.click_count == 0:
        link.click_count = 512
    return req, link


async def _ensure_extra_requisitions(db, org, admin, now) -> None:
    for spec in fx.EXTRA_REQUISITIONS:
        if await _req_by_code(db, org.id, spec["code"]) is not None:
            continue
        # Builder-shaped screening fields → Kandidly JSON-Schema, using the
        # same conversion the console builder does so the round trip is
        # lossless (x-builder-type preserved on each property).
        template = await _create_template(
            db,
            org.id,
            admin.id,
            interview_type=spec["interview_type"],
            title=f"{spec['title']} KYI",
            schema=builder_fields_to_schema(spec["screening_fields"]),
            hints={"full_name": {"use_in_plan": False}},
            now=now,
        )
        rubric = await _create_rubric(
            db,
            org.id,
            admin.id,
            interview_type=spec["interview_type"],
            title=f"{spec['title']} Rubric",
            criteria=_rubric_rows_to_tuples(spec["rubric"]),
            now=now,
        )
        await db.flush()
        close_in = spec.get("close_in_days")
        end_date = (
            (now + timedelta(days=close_in)).replace(hour=23, minute=59, second=0, microsecond=0)
            if close_in is not None
            else None
        )
        req = Requisition(
            id=new_id(),
            org_id=org.id,
            code=spec["code"],
            title=spec["title"],
            interview_type=spec["interview_type"],
            domain=spec["domain"],
            technical_requirements=spec["skills"],
            role_objective=spec["objective"],
            sample_questions=[
                {"id": f"sq-{i + 1}", "text": q} for i, q in enumerate(spec["sample_questions"])
            ],
            form_template_id=template.id,
            rubric_id=rubric.id,
            status=spec["status"],
            interview_config=InterviewConfig(tone=spec["tone"]).model_dump(),
            created_by=admin.id,
            end_date=end_date,
            closes_at=end_date,
        )
        db.add(req)
        await db.flush()
        db.add(
            InviteLink(
                id=new_id(),
                requisition_id=req.id,
                token=generate_token(),
                kind="open",
                use_count=spec["uses"],
                click_count=spec["clicks"],
                created_by=admin.id,
            )
        )


# --------------------------------------------------------------------------- #
# interview pipelines (flagship requisition)
# --------------------------------------------------------------------------- #
_STATE_CHAIN = [
    "registered",
    "form_in_progress",
    "form_submitted",
    "plan_ready",
    "in_lobby",
    "in_interview",
    "completed",
    "scored",
]

_PLAN_NODES = [
    ("intro", "Introduction", "Welcome and format overview.", []),
    (
        "topic",
        "Complex system deep-dive",
        "Tell me about the most complex system you have built.",
        ["system_design_depth", "ownership"],
    ),
    (
        "topic",
        "Failure modes & consistency",
        "How did that system behave under partial failure?",
        ["distributed_systems"],
    ),
    (
        "topic",
        "Debugging rigor",
        "Walk me through a production issue you root-caused.",
        ["problem_solving", "communication"],
    ),
    ("wrap", "Wrap-up", "Questions for us; closing.", []),
]


async def _seed_pipeline(db, case: dict, req, template, link, recruiter, media_ok: bool) -> bool:
    candidate = await _get_or_create_user(db, case["email"], "candidate", display_name=case["name"])
    existing = (
        await db.execute(
            select(Application.id).where(
                Application.requisition_id == req.id, Application.candidate_id == candidate.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    now = datetime.now(UTC)
    started = now - timedelta(days=case["days_ago"], hours=3)
    ended = started + timedelta(seconds=case["duration_s"])
    reviewed = case["decision"] is not None
    final_state = "reviewed" if reviewed else "scored"

    # Application with a realistic state history.
    chain = _STATE_CHAIN + (["reviewed"] if reviewed else [])
    t0 = started - timedelta(days=1)
    stamps: dict[str, str] = {}
    app = Application(
        id=new_id(),
        requisition_id=req.id,
        candidate_id=candidate.id,
        invite_link_id=link.id,
        state=final_state,
        state_timestamps={},
    )
    db.add(app)
    await db.flush()
    prev = None
    for i, state in enumerate(chain):
        ts = (
            t0 + timedelta(hours=2 * i)
            if state not in ("scored", "reviewed")
            else (
                ended + timedelta(minutes=20) if state == "scored" else ended + timedelta(hours=8)
            )
        )
        stamps[state] = ts.isoformat()
        actor = "admin" if state == "reviewed" else ("system" if state == "scored" else "candidate")
        db.add(
            ApplicationEvent(application_id=app.id, from_state=prev, to_state=state, actor=actor)
        )
        prev = state
    app.state_timestamps = stamps
    link.use_count += 1

    submission = FormSubmission(
        id=new_id(),
        application_id=app.id,
        template_id=template.id,
        answers={
            "full_name": case["name"],
            "current_role": "Backend Engineer",
            "years_python": 4 + (case["duration_s"] % 5),
            "kafka_rating": 3,
            "domains": ["ecommerce"],
            "complex_system": case["story"],
            "open_source": "No",
        },
        resume_parse_status="skipped",
        submitted_at=started - timedelta(days=1, hours=-4),
    )
    db.add(submission)
    await db.flush()
    app.form_submission_id = submission.id

    db.add(
        Consent(
            id=new_id(),
            application_id=app.id,
            user_id=candidate.id,
            consent_version="v1-2026-07",
            recording_ack=True,
            monitoring_ack=True,
        )
    )

    seq_val = (await db.execute(sa_text("SELECT nextval('interview_code_seq')"))).scalar_one()
    interview = Interview(
        id=new_id(),
        application_id=app.id,
        requisition_id=req.id,
        code=f"INT-{seq_val}",
        status="finalized",
        started_at=started,
        ended_at=ended,
        elapsed_active_seconds=case["duration_s"],
        end_reason="completed",
    )
    interview.room_name = f"kndl-{interview.id}"
    db.add(interview)
    await db.flush()
    app.interview_id = interview.id

    plan = QuestionPlan(
        id=new_id(),
        interview_id=interview.id,
        status="ready",
        generated_by_model="seed",
        prompt_version="v1",
        total_budget_seconds=1500,
        meta={"source": "seed"},
    )
    db.add(plan)
    await db.flush()
    nodes = []
    for pos, (node_type, title, seed_q, targets) in enumerate(_PLAN_NODES):
        node = QuestionPlanNode(
            id=new_id(),
            plan_id=plan.id,
            position=pos,
            node_type=node_type,
            title=title,
            seed_question=seed_q,
            target_criteria=targets,
            difficulty=3,
            soft_budget_seconds=300,
            priority=pos + 1,
            state="done",
        )
        db.add(node)
        nodes.append(node)
    await db.flush()

    script = fx.transcript_script(case["name"], case["story"])
    turn_gap = case["duration_s"] / len(script)
    # Q/A pairs 0-1→intro, 2-5→system, 6-9→failure/consistency, 10-13→debugging/design, 14-15→wrap
    node_for_turn = [0, 0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4]
    turns: list[Turn] = []
    for i, (speaker, text, decision) in enumerate(script):
        t_start = started + timedelta(seconds=int(i * turn_gap))
        turn = Turn(
            id=new_id(),
            interview_id=interview.id,
            node_id=nodes[node_for_turn[i]].id,
            seq=i + 1,
            speaker=speaker,
            text=text,
            started_at=t_start,
            ended_at=t_start + timedelta(seconds=int(turn_gap * 0.8)),
            decision=decision,
        )
        db.add(turn)
        turns.append(turn)
    await db.flush()

    job = ScoringJob(
        id=new_id(),
        interview_id=interview.id,
        status="done",
        runs_requested=3,
        model="seed",
        prompt_version="v1",
        completed_at=ended + timedelta(minutes=18),
    )
    db.add(job)
    await db.flush()

    # Candidate answer turns to quote as evidence per criterion.
    evidence_turn = {
        "system_design_depth": turns[3],
        "distributed_systems": turns[5],
        "ownership": turns[3],
        "problem_solving": turns[9],
        "communication": turns[7],
    }
    evaluations_data: list[dict] = []
    for key, runs in case["anchors"].items():
        quote_source = evidence_turn[key]
        evidence = [{"turn_id": str(quote_source.id), "quote": quote_source.text[:120]}]
        for run_index, score in enumerate(runs):
            db.add(
                CriterionScore(
                    id=new_id(),
                    scoring_job_id=job.id,
                    run_index=run_index,
                    criterion_key=key,
                    score=score,
                    confidence=0.85,
                    evidence=evidence,
                    rationale=f"Run {run_index + 1} assessment of {key}.",
                )
            )
        score100 = anchor_to_score100(float(median(runs)))
        disagreement = (max(runs) - min(runs)) >= 2
        db.add(
            Evaluation(
                id=new_id(),
                interview_id=interview.id,
                criterion_key=key,
                final_score=score100,
                method="median",
                disagreement=disagreement,
                needs_review=disagreement,
                evidence=evidence,
                rationale=f"Median of {len(runs)} scoring runs for {key}.",
            )
        )
        evaluations_data.append({"criterion_key": key, "final_score": score100})

    overall = round(
        sum(e["final_score"] * WEIGHTS[e["criterion_key"]] for e in evaluations_data) / 100.0, 2
    )
    strengths = [
        f"{e['criterion_key']}: score {e['final_score']:.0f}"
        for e in evaluations_data
        if e["final_score"] >= 75.0
    ]
    concerns = [
        f"{e['criterion_key']}: score {e['final_score']:.0f}"
        for e in evaluations_data
        if e["final_score"] <= 25.0
    ]
    coverage = [
        {"node_id": str(n.id), "title": n.title, "state": n.state, "skip_reason": None}
        for n in nodes
    ]
    report = Report(
        id=new_id(),
        interview_id=interview.id,
        overall_score=overall,
        summary=(
            f"{case['name']} interviewed for {req.title}. Overall score "
            f"{overall:.1f}/100 across {len(evaluations_data)} criteria."
        ),
        strengths=strengths,
        concerns=concerns,
        coverage=coverage,
        proctoring_summary={"visibility_hidden": 1, "identity_verdict": "consistent"},
        status="final" if reviewed else "draft",
        reviewed_by=recruiter.id if reviewed else None,
        reviewed_at=ended + timedelta(hours=8) if reviewed else None,
        review_notes=case["notes"],
        review_decision=case["decision"],
    )
    db.add(report)
    if reviewed:
        db.add(
            AuditLog(
                actor_id=recruiter.id,
                action="report.review",
                entity_type="report",
                entity_id=report.id,
                meta={"decision": case["decision"], "interview_id": str(interview.id)},
            )
        )

    db.add(
        ProctoringEvent(
            interview_id=interview.id,
            application_id=app.id,
            source="browser",
            type="visibility_hidden",
            severity="low",
            payload={"seconds": 4},
            client_ts=started + timedelta(seconds=250),
        )
    )

    if media_ok:
        # Placeholder proctor snapshots.
        for offset_s, signal in fx.SNAPSHOT_PLAN:
            captured = started + timedelta(seconds=offset_s)
            key = storage.snapshot_key(interview.id, int(captured.timestamp() * 1000))
            await storage.put_object(storage.BUCKET_SNAPSHOTS, key, WEBP_1PX, "image/webp")
            f = StoredFile(
                id=new_id(),
                bucket=storage.BUCKET_SNAPSHOTS,
                key=key,
                mime="image/webp",
                bytes=len(WEBP_1PX),
                created_by=candidate.id,
            )
            db.add(f)
            await db.flush()
            db.add(
                ProctoringSnapshot(
                    id=new_id(),
                    interview_id=interview.id,
                    file_id=f.id,
                    captured_at=captured,
                    faces_detected=1,
                    face_present=True,
                    analyzed=True,
                    signal=signal,
                )
            )

        # Generated audio recording + waveform peaks.
        variant = case["days_ago"] % 6
        audio, peaks = _gen_wav(variant)
        key = storage.recording_key(interview.id, "wav")
        await storage.put_object(storage.BUCKET_RECORDINGS, key, audio, "audio/wav")
        f = StoredFile(
            id=new_id(),
            bucket=storage.BUCKET_RECORDINGS,
            key=key,
            mime="audio/wav",
            bytes=len(audio),
            created_by=candidate.id,
        )
        db.add(f)
        await db.flush()
        interview.audio_recording_id = f.id
        interview.audio_waveform = {
            "version": 1,
            "peaks": peaks,
            "bins": len(peaks),
            "duration_seconds": 30,
        }
    return True


# --------------------------------------------------------------------------- #
# purge (clean slate for `--reset`)
# --------------------------------------------------------------------------- #
# Everything except the migration bookkeeping and the default organization row
# (created by migration 0003; the seed reads it back via _ensure_org).
_PRESERVE_TABLES = frozenset({"alembic_version", "organizations"})


async def purge(db) -> None:
    """Delete all seeded and organic data for a clean re-seed.

    TRUNCATE ... CASCADE clears dependents regardless of FK order; RESTART
    IDENTITY resets serial columns owned by the truncated tables. The two
    standalone code sequences aren't owned by any table, so reset them
    explicitly. Orphaned MinIO objects from prior seeds are harmless (new
    interviews get fresh keys) and are left in place.
    """
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in _PRESERVE_TABLES]
    quoted = ", ".join(f'"{name}"' for name in tables)
    await db.execute(sa_text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    for seq in ("requisition_code_seq", "interview_code_seq"):
        await db.execute(sa_text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
    await db.commit()
    print(f"purged {len(tables)} data tables (preserved {', '.join(sorted(_PRESERVE_TABLES))})")


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
async def seed(reset: bool = False) -> None:
    media_ok = await _probe_s3()
    async with SessionLocal() as db:
        if reset:
            await purge(db)
        org = await _ensure_org(db)
        now = datetime.now(UTC)

        admin = await _get_or_create_user(
            db, "admin@kandidly.dev", "admin", display_name="Alex Admin", org_id=org.id
        )
        recruiter = await _get_or_create_user(
            db, "recruiter@kandidly.dev", "recruiter", display_name="Riya Recruiter", org_id=org.id
        )
        cand1 = await _get_or_create_user(
            db, "candidate1@kandidly.dev", "candidate", display_name="Casey Candidate"
        )
        cand2 = await _get_or_create_user(
            db, "candidate2@kandidly.dev", "candidate", display_name="Chris Candidate"
        )

        await _ensure_catalog(db, org.id, admin.id)
        flagship, flagship_link = await _ensure_flagship(db, org, admin, now)
        await _ensure_extra_requisitions(db, org, admin, now)

        template = await db.get(FormTemplate, flagship.form_template_id)

        # Interview pipelines: idempotent per seed candidate (organic
        # applications from live testing may coexist on the flagship).
        created = 0
        for case in fx.INTERVIEW_CASES:
            if await _seed_pipeline(
                db, case, flagship, template, flagship_link, recruiter, media_ok
            ):
                created += 1
        print(
            f"seeded {created} interview pipelines on {FLAGSHIP_CODE} "
            f"({len(fx.INTERVIEW_CASES) - created} already present)"
        )

        await db.commit()
        _print_creds(admin, recruiter, cand1, cand2, flagship_link.token)


def _print_creds(admin, recruiter, cand1, cand2, token) -> None:
    print("\n=== Kandidly dev seed ===")
    for u in (admin, recruiter, cand1, cand2):
        print(f"{u.role:10s} {u.email:28s} dev-token: {_dev_token(u)}")
    if token:
        print(f"\nopen invite link token: {token}")
        print(f"landing: /i/{token}")
    print("Use dev tokens as `Authorization: Bearer <token>` with AUTH_DEV_MODE=true.\n")


if __name__ == "__main__":
    import sys

    asyncio.run(seed(reset="--reset" in sys.argv[1:]))
