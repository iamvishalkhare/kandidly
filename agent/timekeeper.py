"""Active-time clock + wrap/stop triggers (SPEC §8.8). The clock advances only
while the interview status is `live` (pauses on disconnect). Pure logic with an
injectable `now` so the state machine is unit-testable against a simulated clock.
"""

from __future__ import annotations

from dataclasses import dataclass

# Phases returned by phase(); drive the timekeeper's layered enforcement.
PHASE_NORMAL = "normal"
PHASE_WRAP = "wrap"  # Layer 2: forced wrap window
PHASE_HARD_STOP = "hard_stop"  # Layer 3: speak HARD_CLOSE_LINE, end(time_cap)
PHASE_DISCONNECT = "disconnect"  # backstop: unconditional room disconnect

HARD_DISCONNECT_GRACE = 30  # seconds past max_duration (SPEC §8.8 Layer 3)


@dataclass
class Timekeeper:
    max_duration_seconds: int
    wrap_trigger_seconds: int
    # Accumulated active seconds from completed live intervals.
    elapsed_active_seconds: int = 0
    # Monotonic-ish timestamp (seconds) of the current live interval start, or None.
    _live_since: float | None = None

    # -- interval accounting -------------------------------------------------
    def mark_live(self, now: float) -> None:
        if self._live_since is None:
            self._live_since = now

    def mark_paused(self, now: float) -> None:
        if self._live_since is not None:
            self.elapsed_active_seconds += int(now - self._live_since)
            self._live_since = None

    def elapsed(self, now: float) -> int:
        base = self.elapsed_active_seconds
        if self._live_since is not None:
            base += int(now - self._live_since)
        return base

    def remaining(self, now: float) -> int:
        return max(0, self.max_duration_seconds - self.elapsed(now))

    # -- phase ---------------------------------------------------------------
    def phase(self, now: float) -> str:
        e = self.elapsed(now)
        if e >= self.max_duration_seconds + HARD_DISCONNECT_GRACE:
            return PHASE_DISCONNECT
        if e >= self.max_duration_seconds:
            return PHASE_HARD_STOP
        if e >= self.max_duration_seconds - self.wrap_trigger_seconds:
            return PHASE_WRAP
        return PHASE_NORMAL

    def in_wrap_or_later(self, now: float) -> bool:
        return self.phase(now) in (PHASE_WRAP, PHASE_HARD_STOP, PHASE_DISCONNECT)

    def time_state(self, now: float, node_overrun_s: int = 0) -> dict:
        """The `{elapsed_s, remaining_s, node_overrun_s}` block injected into
        every interviewer LLM call (SPEC §8.7)."""
        return {
            "elapsed_s": self.elapsed(now),
            "remaining_s": self.remaining(now),
            "node_overrun_s": node_overrun_s,
            "phase": self.phase(now),
        }
