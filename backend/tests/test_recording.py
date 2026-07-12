"""Recording pipeline pure helpers (jobs/recording.py, api/candidate.py) and
the console integrity aggregation (api/console.py)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.api.candidate import _RECORDING_GRACE_S, _recording_window_open
from app.api.console import integrity_verdict
from app.domain.integrity import integrity_band
from app.jobs.recording import _head_trim_seconds, compute_peaks


# --------------------------------------------------------------------------- #
# compute_peaks
# --------------------------------------------------------------------------- #
def _pcm_sine(seconds: float, rate: int = 8000, amplitude: float = 0.5) -> bytes:
    out = bytearray()
    for i in range(int(seconds * rate)):
        v = int(amplitude * 32767 * math.sin(2 * math.pi * 220 * i / rate))
        out += v.to_bytes(2, "little", signed=True)
    return bytes(out)


def test_compute_peaks_duration_and_scale():
    peaks, duration = compute_peaks(_pcm_sine(4.0), bins=64, rate=8000)
    assert abs(duration - 4.0) < 0.01
    assert len(peaks) == 64
    # 0.5 amplitude sine → peaks around 50, never above 100.
    assert all(0 <= p <= 100 for p in peaks)
    assert max(peaks) in range(45, 56)


def test_compute_peaks_silence():
    peaks, duration = compute_peaks(b"\x00\x00" * 8000, bins=16, rate=8000)
    assert abs(duration - 1.0) < 0.01
    assert peaks == [0] * 16


def test_compute_peaks_empty():
    peaks, duration = compute_peaks(b"")
    assert peaks == []
    assert duration == 0.0


def test_compute_peaks_odd_byte_ignored():
    peaks, duration = compute_peaks(_pcm_sine(1.0) + b"\x7f", bins=8, rate=8000)
    assert abs(duration - 1.0) < 0.01
    assert len(peaks) == 8


# --------------------------------------------------------------------------- #
# head-trim alignment
# --------------------------------------------------------------------------- #
def test_head_trim_normal_offset():
    started = datetime(2026, 7, 10, 12, 0, 5, tzinfo=UTC)
    manifest = {"started_at": "2026-07-10T12:00:00+00:00"}
    assert _head_trim_seconds(manifest, started) == 5.0


def test_head_trim_clamps_clock_skew():
    started = datetime(2026, 7, 10, 12, 5, 0, tzinfo=UTC)
    manifest = {"started_at": "2026-07-10T12:00:00+00:00"}  # 300s > cap
    assert _head_trim_seconds(manifest, started) == 0.0


def test_head_trim_negative_or_missing():
    started = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
    assert _head_trim_seconds({"started_at": "2026-07-10T12:00:10+00:00"}, started) == 0.0
    assert _head_trim_seconds({}, started) == 0.0
    assert _head_trim_seconds({"started_at": "not-a-date"}, started) == 0.0
    assert _head_trim_seconds({"started_at": "2026-07-10T12:00:00+00:00"}, None) == 0.0


# --------------------------------------------------------------------------- #
# recording upload window
# --------------------------------------------------------------------------- #
def _interview(status: str, ended_ago_s: int | None = None):
    ended_at = (
        datetime.now(UTC) - timedelta(seconds=ended_ago_s) if ended_ago_s is not None else None
    )
    return SimpleNamespace(status=status, ended_at=ended_at)


def test_window_open_while_running():
    for status in ("live", "paused", "wrap_up"):
        assert _recording_window_open(_interview(status))


def test_window_grace_after_end():
    assert _recording_window_open(_interview("ended", ended_ago_s=30))
    assert _recording_window_open(_interview("finalized", ended_ago_s=_RECORDING_GRACE_S - 5))
    assert not _recording_window_open(_interview("finalized", ended_ago_s=_RECORDING_GRACE_S + 5))


def test_window_closed_without_end_timestamp():
    assert not _recording_window_open(_interview("created"))
    assert not _recording_window_open(_interview("finalized"))


# --------------------------------------------------------------------------- #
# integrity verdict
# --------------------------------------------------------------------------- #
def test_integrity_pending_when_nothing_analyzed():
    assert integrity_verdict({}, {}, frame_count=6, analyzed_count=0) == "pending"


def test_integrity_flagged_on_signals_or_high_events():
    assert integrity_verdict({"no_face": 2}, {}, 6, 6) == "flagged"
    assert integrity_verdict({"multiple_faces": 1}, {}, 6, 6) == "flagged"
    assert integrity_verdict({}, {"high": 1}, 6, 6) == "flagged"
    # camera denied: no frames at all, but a high-severity camera_off event
    assert integrity_verdict({}, {"high": 1}, 0, 0) == "flagged"


def test_integrity_warn_on_soft_signals():
    assert integrity_verdict({"attention_shift": 1, "clear": 5}, {}, 6, 6) == "warn"
    assert integrity_verdict({"low_light": 1}, {}, 6, 6) == "warn"
    assert integrity_verdict({}, {"medium": 2}, 6, 6) == "warn"


def test_integrity_clear():
    assert integrity_verdict({"clear": 6}, {"low": 3, "info": 5}, 6, 6) == "clear"
    assert integrity_verdict({}, {}, 0, 0) == "clear"


def test_integrity_partial_analysis_not_pending():
    assert integrity_verdict({"clear": 3}, {}, frame_count=6, analyzed_count=3) == "clear"


# --------------------------------------------------------------------------- #
# LLM integrity score: banding + verdict precedence
# --------------------------------------------------------------------------- #
def test_integrity_band_boundaries():
    assert integrity_band(100) == "90-100"
    assert integrity_band(90) == "90-100"
    assert integrity_band(89) == "60-89"
    assert integrity_band(60) == "60-89"
    assert integrity_band(59) == "40-59"
    assert integrity_band(40) == "40-59"
    assert integrity_band(39) == "under-40"
    assert integrity_band(0) == "under-40"


def test_integrity_score_overrides_heuristic():
    # A flagged-looking heuristic loses to a clean LLM score, and vice versa.
    assert integrity_verdict({"no_face": 3}, {"high": 1}, 6, 6, score=95) == "clear"
    assert integrity_verdict({"clear": 6}, {}, 6, 6, score=70) == "warn"
    assert integrity_verdict({"clear": 6}, {}, 6, 6, score=45) == "flagged"
    assert integrity_verdict({"clear": 6}, {}, 6, 6, score=10) == "flagged"
    # Score also settles interviews the heuristic would call pending.
    assert integrity_verdict({}, {}, frame_count=6, analyzed_count=0, score=95) == "clear"
