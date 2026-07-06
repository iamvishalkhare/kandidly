from __future__ import annotations

from datetime import UTC, datetime, date
import pytest
from pydantic import ValidationError

from app.api.console import _closes_at_from, ConsoleRequisitionIn


def test_closes_at_from():
    # None returns None
    assert _closes_at_from(None) is None
    assert _closes_at_from("") is None

    # Valid YYYY-MM-DD date returns end of day UTC
    closes = _closes_at_from("2026-02-28")
    assert closes is not None
    assert closes.year == 2026
    assert closes.month == 2
    assert closes.day == 28
    assert closes.hour == 23
    assert closes.minute == 59
    assert closes.second == 59
    assert closes.tzinfo == UTC

    # Valid datetime string returns exact datetime
    closes_dt = _closes_at_from("2026-02-28T15:30:00")
    assert closes_dt is not None
    assert closes_dt.year == 2026
    assert closes_dt.month == 2
    assert closes_dt.day == 28
    assert closes_dt.hour == 15
    assert closes_dt.minute == 30
    assert closes_dt.second == 0
    assert closes_dt.tzinfo == UTC


def test_console_requisition_in_validation():
    # Valid end_date string (date)
    payload = {
        "title": "SWE",
        "domain": "Eng",
        "objective": "Build things",
        "skills": ["Python"],
        "tone": "conversational",
        "end_date": "2026-02-28",
        "proctoring_enabled": True,
        "sample_questions": [],
        "screening_fields": [],
        "rubric": [],
        "deploy": True,
    }
    req_in = ConsoleRequisitionIn(**payload)
    assert req_in.end_date == "2026-02-28"

    # Valid end_date string (datetime)
    payload["end_date"] = "2026-02-28T15:30"
    req_in_dt = ConsoleRequisitionIn(**payload)
    assert req_in_dt.end_date == "2026-02-28T15:30"

    # Invalid end_date string format
    payload["end_date"] = "2026-02-30T25:00"  # Invalid hour and day
    with pytest.raises(ValidationError):
        ConsoleRequisitionIn(**payload)

    # Empty/whitespace end_date string
    payload["end_date"] = "  "
    req_in_empty = ConsoleRequisitionIn(**payload)
    assert req_in_empty.end_date is None
