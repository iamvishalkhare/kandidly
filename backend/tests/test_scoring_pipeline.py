"""Phase-3 scoring pipeline tests (SPEC §11.2–11.5, §18.1).

All tests are pure-function tests against in-memory structures — no DB, no
network, no provider keys required.  We deliberately avoid aiosqlite because
JSONB/ARRAY/INET columns don't compile on SQLite; instead the core logic is
extracted into pure functions and tested directly.

Test coverage:
- Evidence assembly: targeted turns + note-referenced turns + adjacency dedupe
- Evidence assembly: coverage gap detection
- Quote verification integration: a fake quote drops the run and flips needs_review
- Aggregation math: median of 3 runs, disagreement flag, overall weighted score
- Report fallback path when the report LLM fails
- Prompt filling helpers
- Abandoned-interview caveat in fallback report
"""

from __future__ import annotations

from app.domain.evidence import EvidencePacket, build_evidence_packet
from app.domain.scoring import RunScore, aggregate_runs, filter_evidence
from app.jobs.interviews import (
    _compute_overall_score,
    _fallback_report_draft,
    _fill_report_prompt,
    _fill_score_prompt,
)
from app.llm.schemas import ReportDraft

# ---------------------------------------------------------------------------
# Fixtures: shared plain-dict data
# ---------------------------------------------------------------------------


def _make_turns():
    """Five turns, seqs 1–5, with two nodes."""
    return [
        {
            "id": "t1",
            "seq": 1,
            "speaker": "kandidly",
            "text": "Tell me about a system you designed.",
            "node_id": "n1",
        },
        {
            "id": "t2",
            "seq": 2,
            "speaker": "candidate",
            "text": "I designed a distributed cache with consistent hashing.",
            "node_id": "n1",
        },
        {"id": "t3", "seq": 3, "speaker": "kandidly", "text": "Any trade-offs?", "node_id": "n1"},
        {
            "id": "t4",
            "seq": 4,
            "speaker": "candidate",
            "text": "Yes, we chose eventual consistency for availability.",
            "node_id": "n2",
        },
        {
            "id": "t5",
            "seq": 5,
            "speaker": "kandidly",
            "text": "How did you handle conflicts?",
            "node_id": "n2",
        },
    ]


def _make_criterion(key="system_design", weight=40.0):
    return {
        "key": key,
        "name": "System Design",
        "description": "Ability to design scalable systems.",
        "weight": weight,
        "level_anchors": [
            {"level": 1, "anchor": "No evidence"},
            {"level": 2, "anchor": "Basic understanding"},
            {"level": 3, "anchor": "Solid understanding"},
            {"level": 4, "anchor": "Strong design skills"},
            {"level": 5, "anchor": "Expert-level design"},
        ],
    }


# ---------------------------------------------------------------------------
# Evidence assembly tests
# ---------------------------------------------------------------------------


class TestBuildEvidencePacket:
    def test_targeted_turns_included(self):
        """Turns from a node targeting the criterion are collected."""
        turns = _make_turns()
        # n1 targets system_design
        node_tc = {"n1": ["system_design"], "n2": ["communication"]}
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=[],
        )
        ids = {e["turn_id"] for e in packet.transcript_slice}
        # t1, t2, t3 are from n1; t4 is ±1 adjacent to t3 (seq 3 → seq 4 adjacent)
        assert "t1" in ids
        assert "t2" in ids
        assert "t3" in ids

    def test_note_referenced_turns_included(self):
        """
        Turns referenced by evidence_notes are included even if their node
        doesn't target the criterion.
        """
        turns = _make_turns()
        node_tc = {
            "n1": ["communication"],
            "n2": ["communication"],
        }  # n1 doesn't target system_design
        notes = [
            {
                "id": "en1",
                "turn_id": "t2",
                "criterion_key": "system_design",
                "signal": "positive",
                "note": "candidate described consistent hashing",
            },
        ]
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=notes,
        )
        ids = {e["turn_id"] for e in packet.transcript_slice}
        assert "t2" in ids  # directly referenced

    def test_adjacency_context_included(self):
        """±1 adjacent turns are added for context."""
        turns = _make_turns()
        # Only t2 is targeted (seq 2); expect t1 (seq 1) and t3 (seq 3) also included.
        # Force only t2 to be targeted by making t1/t3 belong to "n_other"
        turns_mod = [{**t, "node_id": "n_other"} if t["id"] in ("t1", "t3") else t for t in turns]
        turns_mod[1]["node_id"] = "n1"  # t2 → n1

        notes = []
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns_mod,
            node_target_criteria={"n1": ["system_design"], "n_other": []},
            evidence_notes=notes,
        )
        ids = {e["turn_id"] for e in packet.transcript_slice}
        # t2 targeted → t1 (seq 1) and t3 (seq 3) adjacent
        assert "t1" in ids
        assert "t3" in ids

    def test_deduplication(self):
        """A turn reachable via multiple paths appears only once."""
        turns = _make_turns()
        # t2 is both targeted by its node AND referenced by a note.
        node_tc = {"n1": ["system_design"], "n2": []}
        notes = [
            {
                "id": "en1",
                "turn_id": "t2",
                "criterion_key": "system_design",
                "signal": "positive",
                "note": "dedup test",
            },
        ]
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=notes,
        )
        turn_ids = [e["turn_id"] for e in packet.transcript_slice]
        assert len(turn_ids) == len(set(turn_ids)), "no duplicate turn_ids"

    def test_ordered_by_seq(self):
        """Transcript slice is ordered by seq ascending."""
        turns = _make_turns()
        node_tc = {"n1": ["system_design"], "n2": ["system_design"]}
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=[],
        )
        seqs = []
        turn_by_id = {t["id"]: t for t in turns}
        for e in packet.transcript_slice:
            seqs.append(turn_by_id[e["turn_id"]]["seq"])
        assert seqs == sorted(seqs), "slice must be sorted by seq"

    def test_coverage_gap_detected(self):
        """coverage_note == 'no targeted turns' when no turn's node targets this criterion."""
        turns = _make_turns()
        node_tc = {"n1": ["other_criterion"], "n2": ["other_criterion"]}
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=[],
        )
        assert packet.coverage_note == "no targeted turns"

    def test_no_coverage_gap_when_targeted(self):
        """coverage_note is empty string when at least one turn targets the criterion."""
        turns = _make_turns()
        node_tc = {"n1": ["system_design"], "n2": []}
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=[],
        )
        assert packet.coverage_note == ""

    def test_notes_filtered_by_criterion(self):
        """Notes for other criteria are not included in the packet."""
        turns = _make_turns()
        notes = [
            {
                "id": "en1",
                "turn_id": "t2",
                "criterion_key": "system_design",
                "signal": "positive",
                "note": "relevant",
            },
            {
                "id": "en2",
                "turn_id": "t4",
                "criterion_key": "communication",
                "signal": "positive",
                "note": "irrelevant",
            },
        ]
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria={"n1": [], "n2": []},
            evidence_notes=notes,
        )
        assert all(n["note"] == "relevant" for n in packet.notes)
        assert len(packet.notes) == 1

    def test_cap_drops_oldest_turns(self):
        """When slice exceeds MAX_SLICE_CHARS, oldest turns are dropped."""
        # Create 5 turns each with 8000-char text → total 40_000 > 24_000 cap.
        big_text = "x" * 8000
        turns = [
            {"id": f"t{i}", "seq": i, "speaker": "candidate", "text": big_text, "node_id": "n1"}
            for i in range(1, 6)
        ]
        node_tc = {"n1": ["system_design"]}
        packet = build_evidence_packet(
            criterion=_make_criterion("system_design"),
            all_turns=turns,
            node_target_criteria=node_tc,
            evidence_notes=[],
        )
        total = sum(len(e["text"]) for e in packet.transcript_slice)
        assert total <= 24_000
        # The kept turns should be the latest ones (highest seq).
        if packet.transcript_slice:
            kept_ids = [e["turn_id"] for e in packet.transcript_slice]
            # t5 (seq 5) should be kept, t1 (seq 1) may be dropped.
            assert "t5" in kept_ids


# ---------------------------------------------------------------------------
# Quote verification integration
# ---------------------------------------------------------------------------


class TestQuoteVerificationIntegration:
    """SPEC Phase-3 gate: fake quotes flip needs_review."""

    TURN_TEXT = {
        "t2": "I designed a distributed cache with consistent hashing.",
        "t4": "Yes, we chose eventual consistency for availability.",
    }

    def test_fake_quote_dropped_and_flips_needs_review(self):
        """A fabricated quote causes the run to be invalid (confidence=0, valid=False),
        which triggers needs_review when ALL runs fail verification."""
        runs = [
            RunScore(
                run_index=i,
                score=4,
                confidence=0.8,
                evidence=[{"turn_id": "t2", "quote": "totally fabricated quote never said"}],
                rationale=f"run {i}",
            )
            for i in range(3)
        ]
        for r in runs:
            filter_evidence(r, self.TURN_TEXT)
        # All runs have fake quotes — all invalid.
        assert all(not r.valid for r in runs)
        agg = aggregate_runs(runs, coverage_gap=False)
        assert agg.needs_review is True
        assert agg.evidence == []

    def test_valid_quote_preserved(self):
        """A verbatim substring quote is kept and does NOT invalidate the run."""
        run = RunScore(
            run_index=0,
            score=4,
            confidence=0.8,
            evidence=[{"turn_id": "t2", "quote": "consistent hashing"}],
            rationale="valid",
        )
        filter_evidence(run, self.TURN_TEXT)
        assert run.valid is True
        assert len(run.evidence) == 1

    def test_mixed_quotes_partial_drop(self):
        """Valid quotes are kept; invalid ones dropped. Run stays valid if ≥1 quote survives."""
        run = RunScore(
            run_index=0,
            score=3,
            confidence=0.7,
            evidence=[
                {"turn_id": "t2", "quote": "consistent hashing"},  # valid
                {"turn_id": "t4", "quote": "completely made up"},  # invalid
            ],
            rationale="mixed",
        )
        filter_evidence(run, self.TURN_TEXT)
        assert run.valid is True
        assert len(run.evidence) == 1
        assert run.evidence[0]["quote"] == "consistent hashing"


# ---------------------------------------------------------------------------
# Aggregation math
# ---------------------------------------------------------------------------


class TestAggregationMath:
    TURN_TEXT = {
        "t2": "I designed a distributed cache with consistent hashing.",
    }

    def _make_run(self, idx, score, confidence=0.7):
        return RunScore(
            run_index=idx,
            score=score,
            confidence=confidence,
            evidence=[{"turn_id": "t2", "quote": "consistent hashing"}],
            rationale=f"run {idx}",
        )

    def test_median_of_three_runs(self):
        """Median of [2, 3, 4] is 3.0."""
        runs = [self._make_run(i, s) for i, s in enumerate([2, 3, 4])]
        for r in runs:
            filter_evidence(r, self.TURN_TEXT)
        agg = aggregate_runs(runs, coverage_gap=False)
        assert agg.final_score == 3.0

    def test_disagreement_flag_triggers(self):
        """max-min >= 2 → disagreement=True."""
        runs = [self._make_run(i, s) for i, s in enumerate([2, 3, 4])]
        for r in runs:
            filter_evidence(r, self.TURN_TEXT)
        agg = aggregate_runs(runs, coverage_gap=False)
        assert agg.disagreement is True  # 4 - 2 >= 2

    def test_no_disagreement_within_one(self):
        """Scores within 1 of each other → disagreement=False."""
        runs = [self._make_run(i, s) for i, s in enumerate([3, 3, 4])]
        for r in runs:
            filter_evidence(r, self.TURN_TEXT)
        agg = aggregate_runs(runs, coverage_gap=False)
        assert agg.disagreement is False  # 4 - 3 == 1 < 2
        assert agg.needs_review is False

    def test_coverage_gap_forces_review(self):
        """coverage_gap=True always triggers needs_review regardless of scores."""
        runs = [self._make_run(i, 3) for i in range(3)]
        for r in runs:
            filter_evidence(r, self.TURN_TEXT)
        agg = aggregate_runs(runs, coverage_gap=True)
        assert agg.needs_review is True

    def test_low_confidence_forces_review(self):
        """confidence < 0.3 on any run triggers needs_review."""
        runs = [
            RunScore(0, 3, 0.2, [{"turn_id": "t2", "quote": "consistent hashing"}], "low-conf"),
            RunScore(1, 3, 0.8, [{"turn_id": "t2", "quote": "consistent hashing"}], "high-conf"),
        ]
        for r in runs:
            filter_evidence(r, self.TURN_TEXT)
        agg = aggregate_runs(runs, coverage_gap=False)
        assert agg.needs_review is True

    def test_overall_weighted_score(self):
        """Σ(final_score × weight) / 100, rounded to 2dp."""
        evaluations = [
            {"criterion_key": "system_design", "final_score": 4.0},
            {"criterion_key": "communication", "final_score": 3.0},
        ]
        weights = {"system_design": 60.0, "communication": 40.0}
        result = _compute_overall_score(evaluations, weights)
        # 4.0*60 + 3.0*40 = 240 + 120 = 360 → 360/100 = 3.60
        assert result == 3.60

    def test_overall_score_single_criterion(self):
        """Single criterion with weight 100."""
        evaluations = [{"criterion_key": "k", "final_score": 4.5}]
        weights = {"k": 100.0}
        assert _compute_overall_score(evaluations, weights) == 4.50

    def test_overall_score_rounds_to_two_dp(self):
        """Result is rounded to 2 decimal places."""
        evaluations = [
            {"criterion_key": "a", "final_score": 4.0},
            {"criterion_key": "b", "final_score": 3.0},
            {"criterion_key": "c", "final_score": 2.0},
        ]
        weights = {"a": 33.33, "b": 33.33, "c": 33.34}
        result = _compute_overall_score(evaluations, weights)
        # 4*33.33 + 3*33.33 + 2*33.34 = 133.32 + 99.99 + 66.68 = 299.99 → 3.00
        assert isinstance(result, float)
        # Check it has at most 2 decimal places.
        assert result == round(result, 2)


# ---------------------------------------------------------------------------
# Report fallback path
# ---------------------------------------------------------------------------


class TestReportFallback:
    def _evals(self, scores):
        return [
            {
                "criterion_key": f"c{i}",
                "final_score": s,
                "needs_review": False,
                "rationale": "test",
                "evidence": [],
            }
            for i, s in enumerate(scores)
        ]

    def test_fallback_returns_report_draft(self):
        """_fallback_report_draft returns a ReportDraft instance."""
        draft = _fallback_report_draft(self._evals([50.0, 75.0]), overall_score=62.50)
        assert isinstance(draft, ReportDraft)

    def test_fallback_summary_contains_overall_score(self):
        draft = _fallback_report_draft(self._evals([50.0, 75.0]), overall_score=62.50)
        assert "62.50" in draft.summary

    def test_fallback_strengths_from_high_scores(self):
        """Criteria scoring >=75 (0-100 scale) appear in strengths."""
        evals = self._evals([87.5, 25.0, 50.0])
        draft = _fallback_report_draft(evals, overall_score=54.17)
        assert any("c0" in s for s in draft.strengths)

    def test_fallback_concerns_from_low_scores(self):
        """Criteria scoring <=25 (0-100 scale) appear in concerns."""
        evals = self._evals([87.5, 12.5, 50.0])
        draft = _fallback_report_draft(evals, overall_score=50.0)
        assert any("c1" in s for s in draft.concerns)

    def test_abandoned_interview_prepends_caveat(self):
        """Abandoned interviews get the SPEC §11.1/E5 caveat prepended."""
        draft = _fallback_report_draft(
            self._evals([50.0]), overall_score=50.0, end_reason="abandoned"
        )
        assert draft.summary.startswith("Note: interview was not completed; coverage is partial.")

    def test_normal_interview_no_caveat(self):
        """Non-abandoned interviews do NOT get the caveat."""
        draft = _fallback_report_draft(
            self._evals([50.0]), overall_score=50.0, end_reason="completed"
        )
        assert "coverage is partial" not in draft.summary

    def test_empty_evaluations_no_crash(self):
        """Fallback handles empty evaluations gracefully."""
        draft = _fallback_report_draft([], overall_score=0.0)
        assert isinstance(draft, ReportDraft)
        assert draft.strengths == []
        assert draft.concerns == []


# ---------------------------------------------------------------------------
# Prompt filling helpers
# ---------------------------------------------------------------------------


class TestPromptFilling:
    def _packet(self, coverage_note=""):
        criterion = _make_criterion("sd")
        return EvidencePacket(
            criterion=criterion,
            transcript_slice=[{"turn_id": "t1", "speaker": "candidate", "text": "hello"}],
            notes=[{"turn_id": "t1", "signal": "positive", "note": "good"}],
            coverage_note=coverage_note,
        )

    def test_fill_score_prompt_substitutes_all_placeholders(self):
        template = "{name} {description} {anchors} {slice} {notes} {coverage_note}"
        filled = _fill_score_prompt(template, self._packet())
        # No placeholder brackets should remain.
        assert "{name}" not in filled
        assert "{description}" not in filled
        assert "{anchors}" not in filled
        assert "{slice}" not in filled
        assert "{notes}" not in filled
        assert "{coverage_note}" not in filled

    def test_fill_score_prompt_criterion_name_present(self):
        template = "CRITERION: {name}"
        filled = _fill_score_prompt(template, self._packet())
        assert "System Design" in filled

    def test_fill_score_prompt_coverage_note_present(self):
        template = "{coverage_note}"
        filled = _fill_score_prompt(template, self._packet("no targeted turns"))
        assert "no targeted turns" in filled

    def test_fill_report_prompt_substitutes_all_placeholders(self):
        template = "{evaluations} {coverage} {proctoring} {meta}"
        filled = _fill_report_prompt(
            template,
            evaluations_data=[{"criterion_key": "sd", "final_score": 3.0}],
            coverage=[{"node_id": "n1", "title": "Intro", "state": "done", "skip_reason": None}],
            proctoring_summary={"tab_switch": 2},
            meta={"duration_seconds": 600, "end_reason": "completed"},
        )
        assert "{evaluations}" not in filled
        assert "{coverage}" not in filled
        assert "{proctoring}" not in filled
        assert "{meta}" not in filled
        assert "sd" in filled

    def test_fill_report_prompt_uses_json(self):
        """Values are serialised as JSON (not Python repr) to avoid single-quote ambiguity."""
        template = "{evaluations}"
        filled = _fill_report_prompt(
            template,
            evaluations_data=[{"criterion_key": "sd", "final_score": 3.0}],
            coverage=[],
            proctoring_summary={},
            meta={},
        )
        # JSON uses double quotes, not single quotes.
        assert '"criterion_key"' in filled


# ---------------------------------------------------------------------------
# Score prompt integration with real score_v1.md template
# ---------------------------------------------------------------------------


class TestScorePromptWithRealTemplate:
    """Verify _fill_score_prompt works against the actual score_v1.md file."""

    def test_real_template_filled(self):
        from app.llm.prompts import load_prompt

        template = load_prompt("score", "v1")
        packet = EvidencePacket(
            criterion=_make_criterion("sd"),
            transcript_slice=[
                {"turn_id": "t1", "speaker": "candidate", "text": "distributed cache"}
            ],
            notes=[],
            coverage_note="",
        )
        filled = _fill_score_prompt(template, packet)
        # All placeholders gone.
        for placeholder in (
            "{name}",
            "{description}",
            "{anchors}",
            "{slice}",
            "{notes}",
            "{coverage_note}",
        ):
            assert placeholder not in filled, f"{placeholder!r} was not substituted"
        # Criterion data appears.
        assert "System Design" in filled
