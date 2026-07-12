"""Integrity score banding (pure; unit-tested in tests/test_recording.py).

The final integrity verdict is an LLM score 0-100 over the per-frame vision
analyses (jobs/proctor_vision.review_integrity), reported to reviewers in four
bands. Higher = cleaner.
"""

from __future__ import annotations

from typing import Literal

IntegrityBand = Literal["90-100", "60-89", "40-59", "under-40"]


def integrity_band(score: int) -> IntegrityBand:
    if score >= 90:
        return "90-100"
    if score >= 60:
        return "60-89"
    if score >= 40:
        return "40-59"
    return "under-40"
