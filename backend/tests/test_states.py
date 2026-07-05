"""Table-driven state machine tests (SPEC §18.1). Every allowed transition
passes; every other ordered pair raises invalid_transition (409)."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.domain.states import (
    APPLICATION_ALLOWED,
    APPLICATION_STATES,
    INTERVIEW_ALLOWED,
    INTERVIEW_STATES,
    assert_application_transition,
    assert_interview_transition,
)


def _all_pairs(states):
    for frm in states:
        for to in states:
            yield frm, to


@pytest.mark.parametrize("frm,to", list(_all_pairs(APPLICATION_STATES)))
def test_application_transitions(frm, to):
    allowed = to in APPLICATION_ALLOWED[frm]
    if allowed:
        assert_application_transition(frm, to)  # no raise
    else:
        with pytest.raises(AppError) as ei:
            assert_application_transition(frm, to)
        assert ei.value.code == "invalid_transition"
        assert ei.value.status_code == 409


@pytest.mark.parametrize("frm,to", list(_all_pairs(INTERVIEW_STATES)))
def test_interview_transitions(frm, to):
    allowed = to in INTERVIEW_ALLOWED[frm]
    if allowed:
        assert_interview_transition(frm, to)
    else:
        with pytest.raises(AppError) as ei:
            assert_interview_transition(frm, to)
        assert ei.value.code == "invalid_transition"


def test_unknown_state_rejected():
    with pytest.raises(AppError) as ei:
        assert_application_transition("registered", "banana")
    assert ei.value.code == "validation_error"


def test_terminal_states_have_no_exits():
    for terminal in ("reviewed", "abandoned", "expired"):
        assert APPLICATION_ALLOWED[terminal] == set()
    assert INTERVIEW_ALLOWED["finalized"] == set()
