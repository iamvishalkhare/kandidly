"""InterviewConfig (SPEC §8.4) stored on requisitions.interview_config (JSONB).
max_duration_seconds is clamped to [600, 1800] — 30 min product ceiling (D6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DIFFICULTY_AUTO = "auto"


class ProctoringConfig(BaseModel):
    enabled: bool = True
    snapshot_min_s: int = 5
    snapshot_max_s: int = 10
    browser_events: bool = True
    audio_diarization: bool = True
    identity_check: bool = True

    @model_validator(mode="after")
    def _min_le_max(self) -> ProctoringConfig:
        if self.snapshot_min_s > self.snapshot_max_s:
            raise ValueError("snapshot_min_s must be <= snapshot_max_s")
        return self


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
        # D6: 30-min ceiling, 10-min floor.
        return max(600, min(1800, v))

    @field_validator("difficulty_band")
    @classmethod
    def _band(cls, v):
        if v == "auto":
            return v
        if isinstance(v, int) and 1 <= v <= 5:
            return v
        raise ValueError("difficulty_band must be 'auto' or an integer 1..5")
