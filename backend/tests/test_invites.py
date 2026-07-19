"""domain/invites.py: email normalization, the bulk-upload parser (CSV +
XLSX, header aliases, positional fallback, dedupe/validation), and the
candidate_invite email context. Datastore-free."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from openpyxl import Workbook

from app.domain.invites import (
    MAX_ROWS,
    ParsedInvites,
    candidate_invite_context,
    normalize_email,
    parse_invite_file,
)


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# normalize_email
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Jordan.Lee@Example.COM ", "jordan.lee@example.com"),
        ("plain@example.dev", "plain@example.dev"),
        ("no-at-sign", None),
        ("two@at@signs.com", None),
        ("spaces in@example.com", None),
        ("missing@tld", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


# --------------------------------------------------------------------------- #
# parse_invite_file
# --------------------------------------------------------------------------- #
def test_csv_with_header_any_order():
    data = (
        b"First Name,E-mail,Last Name\nJordan,jordan@example.com,Lee\nSam,sam@example.com,Field\n"
    )
    parsed = parse_invite_file("candidates.csv", data)
    assert parsed == ParsedInvites(
        rows=[
            {"email": "jordan@example.com", "first_name": "Jordan", "last_name": "Lee"},
            {"email": "sam@example.com", "first_name": "Sam", "last_name": "Field"},
        ],
        invalid=[],
        duplicates=0,
    )


def test_csv_headerless_positional():
    data = b"jordan@example.com,Jordan,Lee\nsam@example.com,Sam,Field\n"
    parsed = parse_invite_file("c.csv", data)
    assert [r["email"] for r in parsed.rows] == ["jordan@example.com", "sam@example.com"]
    assert parsed.rows[0]["first_name"] == "Jordan"
    assert parsed.rows[1]["last_name"] == "Field"


def test_csv_normalizes_dedupes_and_reports_invalid_rows():
    data = (
        b"email,first_name,last_name\n"
        b" JORDAN@Example.com ,Jordan,Lee\n"
        b"not-an-email,Bad,Row\n"
        b"jordan@example.com,Dupe,Lee\n"
        b"\n"
        b"sam@example.com,Sam,\n"
    )
    parsed = parse_invite_file("c.csv", data)
    assert [r["email"] for r in parsed.rows] == ["jordan@example.com", "sam@example.com"]
    assert parsed.rows[1]["last_name"] == ""
    assert parsed.invalid == [{"row": 3, "reason": "invalid email"}]
    assert parsed.duplicates == 1


def test_csv_utf8_bom():
    data = "﻿email,first name,last name\nzoë@example.com,Zoë,Läng\n".encode()
    parsed = parse_invite_file("c.csv", data)
    assert parsed.rows == [{"email": "zoë@example.com", "first_name": "Zoë", "last_name": "Läng"}]


def test_xlsx_with_header():
    data = _xlsx(
        [
            ["Email", "First Name", "Last Name"],
            ["jordan@example.com", "Jordan", "Lee"],
            [None, None, None],
            ["sam@example.com", "Sam", "Field"],
        ]
    )
    parsed = parse_invite_file("candidates.xlsx", data)
    assert [r["email"] for r in parsed.rows] == ["jordan@example.com", "sam@example.com"]
    assert parsed.invalid == []


def test_xlsx_headerless_positional():
    data = _xlsx([["jordan@example.com", "Jordan", "Lee"]])
    parsed = parse_invite_file("c.xlsx", data)
    assert parsed.rows == [
        {"email": "jordan@example.com", "first_name": "Jordan", "last_name": "Lee"}
    ]


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("c.txt", b"x", "upload a .csv or .xlsx"),
        ("c.xls", b"x", "upload a .csv or .xlsx"),
        ("c.csv", b"", "no rows"),
        ("c.csv", b"\n\n,,\n", "no rows"),
        ("c.xlsx", b"this is not a zip archive", "could not read the Excel file"),
        ("c.csv", b"x" * (1024 * 1024 + 1), "file too large"),
    ],
)
def test_unusable_files_raise_value_error(filename, data, message):
    with pytest.raises(ValueError, match=message):
        parse_invite_file(filename, data)


def test_row_cap_enforced():
    body = "".join(f"c{i}@example.com,C,{i}\n" for i in range(MAX_ROWS + 1))
    with pytest.raises(ValueError, match="too many rows"):
        parse_invite_file("c.csv", body.encode())


# --------------------------------------------------------------------------- #
# candidate_invite_context
# --------------------------------------------------------------------------- #
def test_candidate_invite_context_formats_valid_until():
    ctx = candidate_invite_context(
        org_name="Acme Talent",
        interview_name="Backend Screen",
        interview_url="https://k.example/i/tok",
        first_name="  Jordan ",
        closes_at=datetime(2026, 7, 31, 23, 59, tzinfo=UTC),
    )
    assert ctx == {
        "org_name": "Acme Talent",
        "interview_name": "Backend Screen",
        "interview_url": "https://k.example/i/tok",
        "candidate_name": "Jordan",
        "valid_until": "July 31, 2026",
    }


def test_candidate_invite_context_without_close_date_or_name():
    ctx = candidate_invite_context(
        org_name="Acme", interview_name="Screen", interview_url="https://k.example/i/tok"
    )
    assert ctx["valid_until"] == ""
    assert ctx["candidate_name"] == ""
