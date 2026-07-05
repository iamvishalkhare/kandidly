"""Phase-1 text-chat interview harness (SPEC §18.5). Temporary admin-facing
driver for the interviewer LLM using the control-prefix protocol (§8.7) — no
voice. Turns persist through the normal tables so scoring/reports work.

The ctrl grammar/override logic here mirrors agent/control.py (the canonical,
unit-tested implementation for the voice path); duplicated because the backend
must not depend on the livekit-laden agent package. Keep the two in sync.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.db.models import Interview, QuestionPlan, QuestionPlanNode, Turn
from app.domain.states import assert_interview_transition
from app.llm.prompts import load_prompt

CTRL_PREFIX = "@@CTRL "
DECISIONS = {"GREET", "ASK", "PROBE", "CLARIFY", "ADVANCE", "WRAP", "CLOSE"}


@dataclass
class Ctrl:
    d: str
    n: str
    f: str
    end: bool


def parse_ctrl_line(first_line: str) -> Ctrl | None:
    if not first_line.startswith(CTRL_PREFIX):
        return None
    try:
        obj = json.loads(first_line[len(CTRL_PREFIX) :].strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or obj.get("d") not in DECISIONS:
        return None
    return Ctrl(
        d=obj["d"],
        n=str(obj.get("n", "")),
        f=str(obj.get("f", ""))[:200],
        end=bool(obj.get("end", False)),
    )


async def _load(db: AsyncSession, interview_id: UUID):
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise AppError("not_found", "Interview not found")
    plan = (
        await db.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview_id))
    ).scalar_one_or_none()
    if plan is None or plan.status == "failed":
        raise AppError("not_ready", "Plan is not ready for this interview")
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
    return interview, plan, nodes


async def _next_seq(db: AsyncSession, interview_id: UUID) -> int:
    mx = (
        await db.execute(select(func.max(Turn.seq)).where(Turn.interview_id == interview_id))
    ).scalar_one()
    return (mx or 0) + 1


def _current_node(nodes) -> QuestionPlanNode:
    for n in nodes:
        if n.state == "active":
            return n
    for n in nodes:
        if n.state == "pending":
            return n
    return nodes[-1]


async def _followups_used(db: AsyncSession, interview_id: UUID, node_id) -> int:
    return (
        await db.execute(
            select(func.count(Turn.id)).where(
                Turn.interview_id == interview_id,
                Turn.node_id == node_id,
                Turn.decision == "PROBE",
            )
        )
    ).scalar_one()


def _elapsed(interview: Interview) -> int:
    if interview.started_at is None:
        return 0
    return int((datetime.now(UTC) - interview.started_at).total_seconds())


async def _call_llm(system_prompt: str, user_message: str) -> str:
    """One interviewer call, plain-text output (control line + utterance).

    [VERIFY-DOC] pydantic-ai Agent free-text output."""
    from pydantic_ai import Agent

    from app.llm.clients import ensure_provider_env

    ensure_provider_env()  # 503 with a clear message when no key is set
    agent = Agent(settings.realtime_llm, system_prompt=system_prompt)
    result = await agent.run(user_message)
    out = getattr(result, "output", None) or getattr(result, "data", None)
    return str(out)


def _build_prompt(interview, nodes, current, recent, followups_used, wrap_phase) -> tuple[str, str]:
    plan_digest = [
        {
            "id": str(n.id),
            "type": n.node_type,
            "title": n.title,
            "state": n.state,
            "budget_s": n.soft_budget_seconds,
        }
        for n in nodes
    ]
    node_detail = {
        "id": str(current.id),
        "type": current.node_type,
        "title": current.title,
        "seed_question": current.seed_question,
        "target_criteria": current.target_criteria,
        "max_followups": current.max_followups,
    }
    max_dur = 1800
    elapsed = _elapsed(interview)
    time_state = {
        "elapsed_s": elapsed,
        "remaining_s": max(0, max_dur - elapsed),
        "phase": "wrap_up" if wrap_phase else "normal",
    }
    system = (
        load_prompt("interviewer", "v1")
        .replace("{followup_state}", f"{followups_used}/{current.max_followups}")
        .replace("{time_state}", json.dumps(time_state))
        .replace("{injection_state}", "none")
        .replace("{plan_digest}", json.dumps(plan_digest))
        .replace("{node_detail}", json.dumps(node_detail))
        .replace("{recent_turns}", json.dumps(recent))
        .replace("{summary}", "")
    )
    user = "Produce your next turn now, starting with the @@CTRL line."
    return system, user


async def _speak(db, interview, nodes, *, llm_raw: str) -> dict:
    """Parse ctrl + apply overrides + persist the kandidly turn. Returns the API payload."""
    current = _current_node(nodes)
    newline = llm_raw.find("\n")
    first_line, spoken = (
        (llm_raw, "") if newline == -1 else (llm_raw[:newline], llm_raw[newline + 1 :].strip())
    )
    ctrl = parse_ctrl_line(first_line)
    parse_error = ctrl is None
    if ctrl is None:
        ctrl = Ctrl(d="PROBE", n=str(current.id), f="", end=False)
        spoken = llm_raw.replace(CTRL_PREFIX, "").strip()  # never speak the raw line

    # Overrides (mirror §8.7): followup cap, wrap phase, empty-remaining.
    followups = await _followups_used(db, interview.id, current.id)
    wrap_phase = interview.status == "wrap_up" or _elapsed(interview) >= 1800 - 180
    remaining = [n for n in nodes if n.state == "pending" and n.id != current.id]
    overrides = []
    if ctrl.d == "PROBE" and followups >= current.max_followups:
        ctrl.d, ctrl.end = "ADVANCE", True
        overrides.append("followup_cap")
    if wrap_phase and ctrl.d != "CLOSE":
        ctrl.d = "WRAP"
        overrides.append("wrap_phase")
    if ctrl.d == "ADVANCE" and not remaining:
        ctrl.d = "WRAP"
        overrides.append("no_remaining_nodes")

    # Node bookkeeping.
    if ctrl.d in ("ADVANCE", "WRAP") or ctrl.end:
        current.state = "done"
        if remaining:
            nxt = remaining[0]
            nxt.state = "active"
    elif current.state == "pending":
        current.state = "active"

    seq = await _next_seq(db, interview.id)
    turn = Turn(
        id=new_id(),
        interview_id=interview.id,
        node_id=current.id,
        seq=seq,
        speaker="kandidly",
        text=spoken,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        decision=ctrl.d,
        meta={
            "harness": True,
            "overrides": overrides,
            **({"raw_ctrl_error": True} if parse_error else {}),
        },
    )
    db.add(turn)

    ended = False
    if ctrl.d == "CLOSE":
        assert_interview_transition(interview.status, "ended") if interview.status in (
            "live",
            "wrap_up",
            "paused",
        ) else None
        interview.status = "ended"
        interview.ended_at = datetime.now(UTC)
        interview.end_reason = "completed"
        interview.elapsed_active_seconds = _elapsed(interview)
        ended = True
    elif ctrl.d == "WRAP" and interview.status == "live":
        interview.status = "wrap_up"

    await db.flush()
    return {
        "turn": {"seq": seq, "speaker": "kandidly", "text": spoken, "decision": ctrl.d},
        "node": {"id": str(current.id), "title": current.title, "state": current.state},
        "overrides": overrides,
        "ended": ended,
    }


async def start(db: AsyncSession, interview_id: UUID) -> dict:
    """Begin (or resume) a text-mode interview: status → live, speak GREET."""
    interview, plan, nodes = await _load(db, interview_id)
    if interview.status == "created":
        assert_interview_transition("created", "lobby")
        interview.status = "lobby"
    if interview.status == "lobby":
        assert_interview_transition("lobby", "live")
        interview.status = "live"
        interview.started_at = interview.started_at or datetime.now(UTC)
    if interview.status in ("ended", "finalized"):
        raise AppError("conflict", "Interview already ended")

    existing = await _next_seq(db, interview_id)
    if existing > 1:  # resuming — return transcript instead of re-greeting
        return {"resumed": True}

    intro = nodes[0]
    intro.state = "active"
    system, user = _build_prompt(interview, nodes, intro, [], 0, False)
    raw = await _call_llm(system, user)
    return await _speak(db, interview, nodes, llm_raw=raw)


async def reply(db: AsyncSession, interview_id: UUID, text: str) -> dict:
    """Persist the candidate's text answer and produce Kandidly's next turn."""
    interview, plan, nodes = await _load(db, interview_id)
    if interview.status not in ("live", "wrap_up"):
        raise AppError("conflict", f"Interview is {interview.status}, not accepting turns")

    current = _current_node(nodes)
    seq = await _next_seq(db, interview_id)
    db.add(
        Turn(
            id=new_id(),
            interview_id=interview_id,
            node_id=current.id,
            seq=seq,
            speaker="candidate",
            text=text,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            meta={"harness": True},
        )
    )
    await db.flush()

    recent_rows = (
        (
            await db.execute(
                select(Turn)
                .where(Turn.interview_id == interview_id)
                .order_by(Turn.seq.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    recent = [{"speaker": t.speaker, "text": t.text} for t in reversed(recent_rows)]
    followups = await _followups_used(db, interview_id, current.id)
    wrap_phase = interview.status == "wrap_up"
    system, user = _build_prompt(interview, nodes, current, recent, followups, wrap_phase)
    raw = await _call_llm(system, user)
    return await _speak(db, interview, nodes, llm_raw=raw)
