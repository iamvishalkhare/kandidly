"""Plan persistence + fallback bank (SPEC §14 generate_plan, §18.4). Shared by
the LLM plan path and the fallback path."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.db.models import QuestionPlan, QuestionPlanNode

_FALLBACK_DIR = Path(__file__).parent / "fallback_plans"


def load_fallback(interview_type: str) -> list[dict]:
    """Load the generic fallback node bank for an interview_type (SPEC §18.4)."""
    path = _FALLBACK_DIR / f"{interview_type}.json"
    if not path.exists():
        path = _FALLBACK_DIR / "swe_backend.json"  # default bank
    return json.loads(path.read_text(encoding="utf-8"))["nodes"]


def assign_criteria_round_robin(nodes: list[dict], criteria_keys: list[str]) -> None:
    """Distribute rubric criteria across topic nodes so every criterion is
    covered (fallback plans carry no rubric-specific targets)."""
    topics = [n for n in nodes if n["node_type"] == "topic"]
    if not topics or not criteria_keys:
        return
    for i, key in enumerate(criteria_keys):
        node = topics[i % len(topics)]
        node.setdefault("target_criteria", [])
        if key not in node["target_criteria"]:
            node["target_criteria"].append(key)


async def write_plan(
    session: AsyncSession,
    *,
    interview_id: UUID,
    nodes: list[dict],
    status: str,
    model: str,
    prompt_version: str,
    total_budget_seconds: int,
) -> QuestionPlan:
    """Persist a plan + ordered nodes (idempotent: replaces any existing plan)."""
    from sqlalchemy import delete, select

    existing = (
        await session.execute(select(QuestionPlan).where(QuestionPlan.interview_id == interview_id))
    ).scalar_one_or_none()
    if existing is not None:
        await session.execute(
            delete(QuestionPlanNode).where(QuestionPlanNode.plan_id == existing.id)
        )
        await session.delete(existing)
        await session.flush()

    plan = QuestionPlan(
        id=new_id(),
        interview_id=interview_id,
        status=status,
        generated_by_model=model,
        prompt_version=prompt_version,
        total_budget_seconds=total_budget_seconds,
    )
    session.add(plan)
    await session.flush()

    for position, n in enumerate(nodes):
        session.add(
            QuestionPlanNode(
                id=new_id(),
                plan_id=plan.id,
                position=position,
                node_type=n["node_type"],
                title=n["title"],
                seed_question=n["seed_question"],
                target_criteria=n.get("target_criteria", []),
                difficulty=n.get("difficulty"),
                soft_budget_seconds=n["soft_budget_seconds"],
                priority=n["priority"],
                max_followups=n.get("max_followups", 2),
                provenance=n.get("provenance", {}),
                state="pending",
            )
        )
    return plan
