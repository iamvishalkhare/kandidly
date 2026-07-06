"""Scoring pure logic (SPEC §11.2–11.4): evidence quote verification and
run aggregation. No LLM, no DB — unit-tested per SPEC §18.1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

_WS = re.compile(r"\s+")

# LLM runs score on the 1–5 rubric anchor scale (criterion_scores.score);
# stored evaluations/reports use 0–100. Conversion happens once, at the
# aggregation persistence boundary.
ANCHOR_MIN = 1
ANCHOR_MAX = 5


def anchor_to_score100(x: float) -> float:
    """Linear map from the 1–5 anchor scale to 0–100 (1→0, 3→50, 5→100)."""
    return round((x - ANCHOR_MIN) / (ANCHOR_MAX - ANCHOR_MIN) * 100.0, 2)


def normalize_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def verify_quote(quote: str, turn_text: str) -> bool:
    """A returned quote MUST be a verbatim (whitespace-normalized) substring of
    the referenced turn's text (SPEC §11.3 anti-hallucination gate)."""
    if not quote.strip():
        return False
    return normalize_ws(quote) in normalize_ws(turn_text)


@dataclass
class RunScore:
    run_index: int
    score: int
    confidence: float
    evidence: list[dict]  # [{"turn_id", "quote"}]
    rationale: str
    valid: bool = True  # set False when all quotes fail verification


def filter_evidence(run: RunScore, turn_text_by_id: dict[str, str]) -> RunScore:
    """Drop non-matching quotes; a run left with zero valid quotes → confidence 0
    and excluded from aggregation (SPEC §11.3)."""
    kept = [
        e
        for e in run.evidence
        if e.get("turn_id") in turn_text_by_id
        and verify_quote(e.get("quote", ""), turn_text_by_id[e["turn_id"]])
    ]
    run.evidence = kept
    if not kept:
        run.confidence = 0.0
        run.valid = False
    return run


@dataclass
class Aggregated:
    final_score: float
    disagreement: bool
    needs_review: bool
    evidence: list[dict] = field(default_factory=list)
    rationale: str = ""
    method: str = "median"


def aggregate_runs(runs: list[RunScore], *, coverage_gap: bool) -> Aggregated:
    """Median of valid runs; disagreement if (max−min) ≥ 2 across runs;
    needs_review on disagreement, any confidence < 0.3, or coverage gap
    (SPEC §11.4). If all runs are invalid → needs_review, empty evidence,
    median of raw scores (SPEC §11.3)."""
    valid = [r for r in runs if r.valid]
    raw_scores = [r.score for r in runs]

    if not valid:
        return Aggregated(
            final_score=float(median(raw_scores)) if raw_scores else 1.0,
            disagreement=(max(raw_scores) - min(raw_scores) >= 2) if raw_scores else False,
            needs_review=True,
            evidence=[],
            rationale="All evidence quotes failed verification; scored on raw values.",
        )

    valid_scores = [r.score for r in valid]
    final = float(median(valid_scores))
    disagreement = (max(valid_scores) - min(valid_scores)) >= 2
    low_conf = any(r.confidence < 0.3 for r in valid)
    needs_review = disagreement or low_conf or coverage_gap

    # Evidence: union from the median-scoring run (fallback: all valid).
    median_runs = [r for r in valid if r.score == round(final)]
    source = median_runs[0] if median_runs else valid[0]
    evidence = source.evidence or [e for r in valid for e in r.evidence]

    return Aggregated(
        final_score=final,
        disagreement=disagreement,
        needs_review=needs_review,
        evidence=evidence,
        rationale=source.rationale,
    )
