"""Plan validation (SPEC §14.1) — code gate run after the plan-generator LLM.
Reject → retry once → fallback generic plan. Pure; operates on plain node dicts
so it can validate both LLM output and the fallback bank."""

from __future__ import annotations

from app.core.errors import AppError

MIN_NODES = 4
MAX_NODES = 9
BUDGET_HEADROOM_SECONDS = 120  # Σ soft_budget ≤ max_duration − 120


class PlanValidationError(AppError):
    def __init__(self, message: str, **detail) -> None:
        super().__init__("validation_error", message, detail=detail)


def validate_plan(
    nodes: list[dict],
    *,
    rubric_criteria_keys: set[str],
    max_duration_seconds: int,
    difficulty_band: str | int,
) -> None:
    """Raise PlanValidationError on any violated rule (SPEC §14.1)."""
    n = len(nodes)
    if not (MIN_NODES <= n <= MAX_NODES):
        raise PlanValidationError(f"node count {n} outside {MIN_NODES}..{MAX_NODES}")

    types = [node["node_type"] for node in nodes]
    if types[0] != "intro":
        raise PlanValidationError("first node must be 'intro'", first=types[0])
    if types[-1] != "wrap":
        raise PlanValidationError("last node must be 'wrap'", last=types[-1])
    if types.count("intro") != 1:
        raise PlanValidationError("exactly one 'intro' node required")
    if types.count("wrap") != 1:
        raise PlanValidationError("exactly one 'wrap' node required")

    # ≥1 candidate_questions node, positioned before the wrap.
    cq_positions = [i for i, t in enumerate(types) if t == "candidate_questions"]
    if not cq_positions:
        raise PlanValidationError("at least one 'candidate_questions' node required")
    if max(cq_positions) >= n - 1:
        raise PlanValidationError("'candidate_questions' must come before 'wrap'")

    # Every rubric criterion appears in ≥1 node's target_criteria.
    covered: set[str] = set()
    for node in nodes:
        covered.update(node.get("target_criteria") or [])
    missing = rubric_criteria_keys - covered
    if missing:
        raise PlanValidationError(
            "rubric criteria not covered by any node", missing=sorted(missing)
        )

    # Σ soft_budget_seconds ≤ max_duration − headroom.
    total_budget = sum(int(node["soft_budget_seconds"]) for node in nodes)
    ceiling = max_duration_seconds - BUDGET_HEADROOM_SECONDS
    if total_budget > ceiling:
        raise PlanValidationError(
            "soft budgets exceed ceiling", total=total_budget, ceiling=ceiling
        )

    # Every topic node has non-empty provenance.source.
    for node in nodes:
        if node["node_type"] == "topic":
            source = (node.get("provenance") or {}).get("source")
            if not source:
                raise PlanValidationError(
                    "topic node missing provenance.source", title=node.get("title")
                )

    # Difficulty within band when band is a fixed integer.
    if isinstance(difficulty_band, int):
        for node in nodes:
            d = node.get("difficulty")
            if d is not None and d != difficulty_band:
                raise PlanValidationError(
                    "node difficulty outside fixed band",
                    node_difficulty=d,
                    band=difficulty_band,
                )
