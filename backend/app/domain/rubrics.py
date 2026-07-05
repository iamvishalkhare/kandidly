"""Rubric publish invariants (SPEC §7.3): weight sum == 100.00; 3..12 criteria;
level_anchors covers levels 1..5 exactly once each."""

from __future__ import annotations

from decimal import Decimal

from app.core.errors import AppError

MIN_CRITERIA = 3
MAX_CRITERIA = 12
REQUIRED_LEVELS = frozenset({1, 2, 3, 4, 5})


def _fail(message: str, **detail) -> AppError:
    return AppError("validation_error", message, detail=detail)


def validate_criteria(criteria: list[dict]) -> None:
    """`criteria` items: {key, name, description, weight, display_order, level_anchors}."""
    n = len(criteria)
    if not (MIN_CRITERIA <= n <= MAX_CRITERIA):
        raise _fail(f"rubric must have {MIN_CRITERIA}..{MAX_CRITERIA} criteria, got {n}")

    keys = [c["key"] for c in criteria]
    if len(set(keys)) != len(keys):
        raise _fail("criterion keys must be unique", keys=keys)

    total = Decimal("0")
    for c in criteria:
        weight = Decimal(str(c["weight"]))
        if weight <= 0:
            raise _fail(f"criterion {c['key']!r} weight must be > 0", key=c["key"])
        total += weight

        anchors = c.get("level_anchors")
        if not isinstance(anchors, list):
            raise _fail(f"criterion {c['key']!r} level_anchors must be a list", key=c["key"])
        levels = [a.get("level") for a in anchors]
        if set(levels) != REQUIRED_LEVELS or len(levels) != 5:
            raise _fail(
                f"criterion {c['key']!r} level_anchors must cover levels 1..5 exactly once",
                key=c["key"],
                levels=levels,
            )
        for a in anchors:
            if not str(a.get("anchor", "")).strip():
                raise _fail(f"criterion {c['key']!r} has an empty anchor", key=c["key"])

    if total != Decimal("100.00"):
        raise _fail(f"criterion weights must sum to 100.00, got {total}", total=str(total))
