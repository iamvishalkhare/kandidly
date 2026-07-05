"""Proctoring severity mapping + event-type registry (SPEC §10.2, §18.1)."""

from __future__ import annotations

from app.domain.proctoring import BROWSER_EVENT_TYPES, SYSTEM_EVENT_TYPES, classify


def test_closed_set_of_browser_types():
    assert "visibility_hidden" in BROWSER_EVENT_TYPES
    assert "page_unload" in BROWSER_EVENT_TYPES
    assert len(BROWSER_EVENT_TYPES) == 12


def test_camera_off_is_high():
    assert classify("camera_off", {}) == "high"


def test_fullscreen_exit_is_low():
    assert classify("fullscreen_exit", {}) == "low"


def test_blur_duration_upgrade():
    assert classify("window_blur", {"duration_s": 2}) == "low"
    assert classify("window_blur", {"duration_s": 6}) == "medium"
    assert classify("visibility_hidden", {"duration_s": 10}) == "medium"


def test_paste_attempt_medium():
    assert classify("paste_attempt", {}) == "medium"


def test_unknown_type_defaults_info():
    assert classify("mystery_event", {}) == "info"


def test_system_types_include_derived():
    for t in ("multiple_faces", "no_face_sustained", "second_voice_detected"):
        assert t in SYSTEM_EVENT_TYPES
