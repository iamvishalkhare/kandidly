"""Proctoring severity mapping + event-type registry (SPEC §10.2, §18.1),
per-requisition config resolution, and the disabled-proctoring ingest gate."""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.domain.proctoring import BROWSER_EVENT_TYPES, SYSTEM_EVENT_TYPES, classify, config_for


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


# --------------------------------------------------------------------------- #
# config_for — the single gate for every camera/proctoring decision
# --------------------------------------------------------------------------- #
def test_config_for_defaults_to_enabled():
    for raw in (None, {}, {"proctoring": {}}):
        cfg = config_for(raw)
        assert cfg.enabled is True
        assert cfg.identity_check is True
        assert cfg.snapshot_interval_s == 10


def test_config_for_reads_the_builder_toggle():
    assert config_for({"proctoring": {"enabled": False}}).enabled is False
    assert config_for({"proctoring": {"enabled": True}}).enabled is True


def test_config_for_per_requisition_interval():
    assert config_for({"proctoring": {"snapshot_interval_s": 30}}).snapshot_interval_s == 30


def test_config_for_tolerates_legacy_snapshot_keys():
    # Older persisted configs carry snapshot_min_s/max_s; pydantic must ignore
    # them as extra keys rather than fail the whole join/ingest path.
    cfg = config_for({"proctoring": {"snapshot_min_s": 5, "snapshot_max_s": 10}})
    assert cfg.enabled is True
    assert cfg.snapshot_interval_s == 10


# --------------------------------------------------------------------------- #
# ingest gate — snapshots/events are refused when proctoring is off (the
# verification selfie is deliberately NOT gated: it is always required)
# --------------------------------------------------------------------------- #
class _FakeDB:
    """Only what _require_proctoring_enabled touches: db.get(Requisition, id)."""

    def __init__(self, requisition):
        self._requisition = requisition

    async def get(self, _model, _pk):
        return self._requisition


class _Req:
    def __init__(self, interview_config):
        self.interview_config = interview_config


async def test_ingest_gate_allows_enabled():
    from uuid import uuid4

    from app.api.candidate import _require_proctoring_enabled

    db = _FakeDB(_Req({"proctoring": {"enabled": True}}))
    await _require_proctoring_enabled(db, uuid4())  # no raise


async def test_ingest_gate_rejects_disabled():
    from uuid import uuid4

    from app.api.candidate import _require_proctoring_enabled

    db = _FakeDB(_Req({"proctoring": {"enabled": False}}))
    with pytest.raises(AppError) as exc:
        await _require_proctoring_enabled(db, uuid4())
    assert exc.value.code == "forbidden"
