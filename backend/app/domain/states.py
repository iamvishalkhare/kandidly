"""State machines (SPEC §8.2 application, §8.3 interview). Pure — no DB. The only
DB write path for application state is domain.applications.transition (SPEC §7
write-path rule 1), which calls assert_application_transition() here first.

Illegal transitions raise AppError(code='invalid_transition') → HTTP 409.
"""

from __future__ import annotations

from app.core.errors import AppError

# --------------------------------------------------------------------------- #
# Application state machine (SPEC §8.2)
# --------------------------------------------------------------------------- #
APPLICATION_STATES: frozenset[str] = frozenset(
    {
        "registered",
        "form_in_progress",
        "form_submitted",
        "plan_ready",
        "in_lobby",
        "in_interview",
        "completed",
        "scored",
        "reviewed",
        "abandoned",
        "expired",
    }
)

# Literal transition table (SPEC §8.2). Every allowed transition is listed;
# any other (from, to) pair is illegal.
#
# TODO(spec-gap): SPEC §8.2 lists "in_interview → abandoned ... partial transcript
# still finalized+scored". The scoring pipeline runs at the interview level and
# attaches a report to the interview row; the application state stays 'abandoned'
# (terminal). There is no abandoned → scored transition in the spec table.
APPLICATION_ALLOWED: dict[str, set[str]] = {
    "registered": {"form_in_progress", "expired"},
    "form_in_progress": {"form_submitted", "expired"},
    "form_submitted": {"plan_ready", "in_lobby", "expired"},
    "plan_ready": {"in_lobby", "expired"},
    # in_lobby is pre-interview; sweep_links_and_apps may expire it past closes_at.
    "in_lobby": {"in_interview", "expired"},
    "in_interview": {"completed", "abandoned"},
    "completed": {"scored"},
    "scored": {"reviewed"},
    "reviewed": set(),
    "abandoned": set(),
    "expired": set(),
}

# State the application is created in (SPEC §8.2 first row).
APPLICATION_INITIAL = "registered"

# --------------------------------------------------------------------------- #
# Interview status machine (SPEC §8.3)
#   created → lobby → live ⇄ paused → wrap_up → ended → finalized
# --------------------------------------------------------------------------- #
INTERVIEW_STATES: frozenset[str] = frozenset(
    {"created", "lobby", "live", "paused", "wrap_up", "ended", "finalized"}
)

INTERVIEW_ALLOWED: dict[str, set[str]] = {
    # "ended" here too: sweep_abandoned force-ends a lobby/created interview
    # whose agent never dispatched/connected in time (SPEC §14).
    "created": {"lobby", "ended"},
    "lobby": {"live", "ended"},
    "live": {"paused", "wrap_up", "ended"},
    "paused": {"live", "ended"},
    "wrap_up": {"ended", "paused"},
    "ended": {"finalized"},
    "finalized": set(),
}

INTERVIEW_INITIAL = "created"


def can_transition(allowed: dict[str, set[str]], frm: str, to: str) -> bool:
    return to in allowed.get(frm, set())


def _assert(
    allowed: dict[str, set[str]], valid: frozenset[str], frm: str, to: str, kind: str
) -> None:
    if to not in valid:
        raise AppError(
            "validation_error",
            f"Unknown {kind} state: {to!r}",
            detail={"state": to},
        )
    if not can_transition(allowed, frm, to):
        raise AppError(
            "invalid_transition",
            f"Illegal {kind} transition {frm!r} → {to!r}",
            detail={"from": frm, "to": to, "kind": kind},
        )


def assert_application_transition(frm: str, to: str) -> None:
    _assert(APPLICATION_ALLOWED, APPLICATION_STATES, frm, to, "application")


def assert_interview_transition(frm: str, to: str) -> None:
    _assert(INTERVIEW_ALLOWED, INTERVIEW_STATES, frm, to, "interview")
