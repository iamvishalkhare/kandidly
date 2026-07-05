"""Timekeeper simulated-clock tests (SPEC §8.8, §18.1)."""

from __future__ import annotations

from timekeeper import (
    PHASE_DISCONNECT,
    PHASE_HARD_STOP,
    PHASE_NORMAL,
    PHASE_WRAP,
    Timekeeper,
)


def _tk():
    return Timekeeper(max_duration_seconds=1800, wrap_trigger_seconds=180)


def test_normal_phase_early():
    tk = _tk()
    tk.mark_live(0.0)
    assert tk.phase(100.0) == PHASE_NORMAL
    assert tk.remaining(100.0) == 1700


def test_wrap_at_t_minus_180():
    tk = _tk()
    tk.mark_live(0.0)
    assert tk.phase(1620.0) == PHASE_WRAP  # 1800 - 180
    assert tk.phase(1619.0) == PHASE_NORMAL


def test_hard_stop_at_max():
    tk = _tk()
    tk.mark_live(0.0)
    assert tk.phase(1800.0) == PHASE_HARD_STOP


def test_disconnect_backstop():
    tk = _tk()
    tk.mark_live(0.0)
    assert tk.phase(1831.0) == PHASE_DISCONNECT


def test_pause_resume_excludes_paused_time():
    tk = _tk()
    tk.mark_live(0.0)
    tk.mark_paused(600.0)  # 600s active accumulated
    assert tk.elapsed(600.0) == 600
    # 5 minutes paused, no accrual:
    assert tk.elapsed(900.0) == 600
    tk.mark_live(900.0)
    assert tk.elapsed(1000.0) == 700  # +100s live


def test_time_state_shape():
    tk = _tk()
    tk.mark_live(0.0)
    ts = tk.time_state(120.0, node_overrun_s=15)
    assert ts["elapsed_s"] == 120
    assert ts["remaining_s"] == 1680
    assert ts["node_overrun_s"] == 15
    assert ts["phase"] == PHASE_NORMAL
