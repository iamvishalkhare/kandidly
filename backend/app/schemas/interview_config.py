"""InterviewConfig (SPEC §8.4) stored on requisitions.interview_config (JSONB).
max_duration_seconds is builder-configurable per requisition and clamped to
[900, 5400] — 15-min floor, 90-min ceiling, 30-min default (supersedes D6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DIFFICULTY_AUTO = "auto"


class ProctoringConfig(BaseModel):
    enabled: bool = True
    # One webcam frame every N seconds. Older persisted configs carry
    # snapshot_min_s/snapshot_max_s, which pydantic ignores as extra keys.
    snapshot_interval_s: int = 10
    browser_events: bool = True
    audio_diarization: bool = True
    identity_check: bool = True


class InterviewConfig(BaseModel):
    max_duration_seconds: int = 1800
    wrap_trigger_seconds: int = 180
    rejoin_grace_seconds: int = 600
    proctoring: ProctoringConfig = Field(default_factory=ProctoringConfig)
    observer_allowed: bool = True
    difficulty_band: Literal["auto"] | int = DIFFICULTY_AUTO  # type: ignore
    tone: Literal["conversational", "friendly", "technical", "structured", "bar_raiser"] = (
        "conversational"
    )
    language: str = "en"

    @field_validator("max_duration_seconds")
    @classmethod
    def _clamp_duration(cls, v: int) -> int:
        # 15-min floor, 90-min ceiling (builder offers 15–90 minutes).
        return max(900, min(5400, v))

    @field_validator("difficulty_band")
    @classmethod
    def _band(cls, v):
        if v == "auto":
            return v
        if isinstance(v, int) and 1 <= v <= 5:
            return v
        raise ValueError("difficulty_band must be 'auto' or an integer 1..5")
