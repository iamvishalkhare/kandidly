"""Prompt assembly + time-note logic in worker.py (pure functions only)."""

from worker import _build_instructions, _time_note, _topic_budgets


def _node(q: str, budget: int | None = None, node_type: str = "topic") -> dict:
    return {"seed_question": q, "soft_budget_seconds": budget, "node_type": node_type}


class TestTopicBudgets:
    def test_scales_soft_budgets_to_interview_clock(self):
        # Two 300s topics against a 600s interview: 85% of the clock split
        # proportionally → ~4 min each, not the raw 5 min from the plan.
        out = _topic_budgets([_node("a", 300), _node("b", 300)], 600)
        assert out == [("a", 4), ("b", 4)]

    def test_proportional_split_keeps_ratios(self):
        # 85% of 1800s split 2:1 → 1020s and 510s → 17 and 8 min (8.5 rounds down).
        out = _topic_budgets([_node("a", 600), _node("b", 300)], 1800)
        assert out == [("a", 17), ("b", 8)]

    def test_even_split_when_budget_missing(self):
        out = _topic_budgets([_node("a", 300), _node("b", None)], 600)
        assert out[0][1] == out[1][1]

    def test_falls_back_to_default_questions(self):
        out = _topic_budgets([], 900)
        assert len(out) == 3
        assert all(m >= 1 for _, m in out)

    def test_excludes_wrap_and_candidate_questions_nodes(self):
        nodes = [
            _node("real", 300),
            _node("bye", 60, node_type="wrap"),
            _node("any questions?", 60, node_type="candidate_questions"),
        ]
        out = _topic_budgets(nodes, 600)
        assert [q for q, _ in out] == ["real"]

    def test_minimum_one_minute_per_topic(self):
        out = _topic_budgets([_node(f"q{i}", 300) for i in range(10)], 120)
        assert all(m == 1 for _, m in out)


class TestTimeNote:
    def test_normal_phase_encourages_pacing_and_depth(self):
        note = _time_note(elapsed=120, remaining=1080, wrap_trigger=180)
        assert "2 min elapsed" in note
        assert "18 min remaining" in note
        assert "probe" in note
        assert "never read aloud" in note

    def test_wrap_phase_directive(self):
        note = _time_note(elapsed=1650, remaining=150, wrap_trigger=180)
        assert "Wrap-up window" in note
        assert "2 min remaining" in note

    def test_final_minute_forces_close(self):
        note = _time_note(elapsed=1750, remaining=50, wrap_trigger=180)
        assert "Time is up" in note
        assert "50 sec remaining" in note


class TestBuildInstructions:
    def test_prompt_carries_duration_budgets_and_time_rules(self):
        boot = {
            "nodes": [_node("Tell me about X.", 300), _node("Tell me about Y.", 300)],
            "config": {"tone": "friendly", "max_duration_seconds": 900},
        }
        prompt = _build_instructions(boot, 900)
        assert "about 15 minutes" in prompt
        assert "1. (about " in prompt
        assert "# Time management" in prompt
        assert "[Time check" in prompt
        assert "friendly" in prompt

    def test_empty_boot_still_produces_full_prompt(self):
        prompt = _build_instructions({}, 600)
        assert "about 10 minutes" in prompt
        assert "# Time management" in prompt
        assert prompt.count("(about ") == 3  # default question bank
