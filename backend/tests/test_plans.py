"""Plan validation (SPEC §14.1, §18.1) + rubric validation (SPEC §7.3)."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.domain.plans import validate_plan
from app.domain.rubrics import validate_criteria

CRITERIA_KEYS = {"a", "b"}


def _node(nt, title, budget, prov="resume.x", crit=None, difficulty=None):
    return {
        "node_type": nt,
        "title": title,
        "seed_question": "q?",
        "soft_budget_seconds": budget,
        "priority": 3,
        "target_criteria": crit or [],
        "provenance": {"source": prov},
        "difficulty": difficulty,
    }


def _valid_plan():
    return [
        _node("intro", "Intro", 60, prov="generic_bank"),
        _node("topic", "T1", 300, crit=["a"]),
        _node("topic", "T2", 300, crit=["b"]),
        _node("candidate_questions", "CQ", 90, prov="generic_bank"),
        _node("wrap", "Wrap", 30, prov="generic_bank"),
    ]


def test_valid_plan_passes():
    validate_plan(
        _valid_plan(),
        rubric_criteria_keys=CRITERIA_KEYS,
        max_duration_seconds=1800,
        difficulty_band="auto",
    )


def test_too_few_nodes():
    with pytest.raises(AppError):
        validate_plan(
            _valid_plan()[:3],
            rubric_criteria_keys=CRITERIA_KEYS,
            max_duration_seconds=1800,
            difficulty_band="auto",
        )


def test_first_must_be_intro():
    plan = _valid_plan()
    plan[0]["node_type"] = "topic"
    with pytest.raises(AppError):
        validate_plan(
            plan,
            rubric_criteria_keys=CRITERIA_KEYS,
            max_duration_seconds=1800,
            difficulty_band="auto",
        )


def test_uncovered_criterion_rejected():
    plan = _valid_plan()
    plan[2]["target_criteria"] = ["a"]  # b now uncovered
    with pytest.raises(AppError):
        validate_plan(
            plan,
            rubric_criteria_keys=CRITERIA_KEYS,
            max_duration_seconds=1800,
            difficulty_band="auto",
        )


def test_budget_ceiling_enforced():
    plan = _valid_plan()
    plan[1]["soft_budget_seconds"] = 5000
    with pytest.raises(AppError):
        validate_plan(
            plan,
            rubric_criteria_keys=CRITERIA_KEYS,
            max_duration_seconds=1800,
            difficulty_band="auto",
        )


def test_topic_needs_provenance():
    plan = _valid_plan()
    plan[1]["provenance"] = {"source": ""}
    with pytest.raises(AppError):
        validate_plan(
            plan,
            rubric_criteria_keys=CRITERIA_KEYS,
            max_duration_seconds=1800,
            difficulty_band="auto",
        )


def test_candidate_questions_before_wrap():
    plan = _valid_plan()
    plan[3], plan[4] = plan[4], plan[3]  # wrap before candidate_questions
    with pytest.raises(AppError):
        validate_plan(
            plan,
            rubric_criteria_keys=CRITERIA_KEYS,
            max_duration_seconds=1800,
            difficulty_band="auto",
        )


def test_difficulty_band_fixed():
    plan = _valid_plan()
    plan[1]["difficulty"] = 5
    with pytest.raises(AppError):
        validate_plan(
            plan, rubric_criteria_keys=CRITERIA_KEYS, max_duration_seconds=1800, difficulty_band=3
        )


# --- rubric validation ------------------------------------------------------
def _crit(key, weight):
    return {
        "key": key,
        "name": f"Criterion {key}",
        "description": f"Description for {key}",
        "weight": weight,
        "level_anchors": [{"level": i, "anchor": f"a{i}"} for i in range(1, 6)],
    }


def test_rubric_weights_must_sum_100():
    validate_criteria([_crit("a", 50), _crit("b", 30), _crit("c", 20)])
    with pytest.raises(AppError):
        validate_criteria([_crit("a", 50), _crit("b", 30), _crit("c", 25)])


def test_rubric_criteria_count_bounds():
    with pytest.raises(AppError):
        validate_criteria([_crit("a", 60), _crit("b", 40)])  # < 3


def test_rubric_anchor_levels_required():
    bad = _crit("a", 100)
    bad["level_anchors"] = bad["level_anchors"][:4]
    with pytest.raises(AppError):
        validate_criteria([bad, _crit("b", 0.0001)])
