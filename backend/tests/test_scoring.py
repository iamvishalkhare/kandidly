"""Quote verification + aggregation (SPEC §11.3, §11.4, §18.1)."""

from __future__ import annotations

from app.domain.scoring import (
    RunScore,
    aggregate_runs,
    anchor_to_score100,
    filter_evidence,
    normalize_ws,
    verify_quote,
)

TURN_TEXT = {"t1": "I used idempotency keys with retry semantics to avoid double charges."}


def test_exact_quote_matches():
    assert verify_quote("idempotency keys with retry semantics", TURN_TEXT["t1"])


def test_whitespace_normalized_match():
    assert verify_quote("idempotency   keys\nwith retry", TURN_TEXT["t1"])


def test_near_miss_dropped():
    assert not verify_quote("idempotency tokens with retry logic", TURN_TEXT["t1"])


def test_empty_quote_dropped():
    assert not verify_quote("   ", TURN_TEXT["t1"])


def test_filter_evidence_zeroes_confidence_when_all_fail():
    run = RunScore(0, 4, 0.8, [{"turn_id": "t1", "quote": "totally fabricated quote"}], "r")
    filter_evidence(run, TURN_TEXT)
    assert run.valid is False
    assert run.confidence == 0.0
    assert run.evidence == []


def test_filter_evidence_keeps_valid_quotes():
    run = RunScore(
        0,
        4,
        0.8,
        [
            {"turn_id": "t1", "quote": "retry semantics"},
            {"turn_id": "t1", "quote": "made this up"},
        ],
        "r",
    )
    filter_evidence(run, TURN_TEXT)
    assert run.valid is True
    assert len(run.evidence) == 1


def test_median_and_disagreement():
    runs = [
        RunScore(0, 2, 0.7, [{"turn_id": "t1", "quote": "retry semantics"}], "r0"),
        RunScore(1, 4, 0.7, [{"turn_id": "t1", "quote": "idempotency keys"}], "r1"),
        RunScore(2, 3, 0.7, [{"turn_id": "t1", "quote": "double charges"}], "r2"),
    ]
    for r in runs:
        filter_evidence(r, TURN_TEXT)
    agg = aggregate_runs(runs, coverage_gap=False)
    assert agg.final_score == 3.0
    assert agg.disagreement is True  # 4 - 2 >= 2
    assert agg.needs_review is True


def test_all_invalid_runs_score_floor():
    # No verifiable evidence anywhere → not assessable → anchor floor (0/100),
    # never the LLMs' unverified raw numbers.
    runs = [RunScore(i, 3, 0.9, [{"turn_id": "t1", "quote": "fake"}], "r") for i in range(3)]
    for r in runs:
        filter_evidence(r, TURN_TEXT)
    agg = aggregate_runs(runs, coverage_gap=False)
    assert agg.needs_review is True
    assert agg.evidence == []
    assert agg.final_score == 1.0
    assert agg.method == "unassessed"


def test_coverage_gap_forces_review():
    runs = [
        RunScore(i, 3, 0.9, [{"turn_id": "t1", "quote": "retry semantics"}], "r") for i in range(3)
    ]
    for r in runs:
        filter_evidence(r, TURN_TEXT)
    agg = aggregate_runs(runs, coverage_gap=True)
    assert agg.needs_review is True


def test_normalize_ws():
    assert normalize_ws("  a\n b\t c ") == "a b c"


class TestAnchorToScore100:
    """Linear 1–5 → 0–100 map used at the aggregation persistence boundary."""

    def test_boundaries(self):
        assert anchor_to_score100(1.0) == 0.0
        assert anchor_to_score100(3.0) == 50.0
        assert anchor_to_score100(5.0) == 100.0

    def test_half_step(self):
        assert anchor_to_score100(3.5) == 62.5

    def test_rounding_two_decimals(self):
        assert anchor_to_score100(2.333) == 33.33
