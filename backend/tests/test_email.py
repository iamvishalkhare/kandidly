"""Email machinery (core/email.py + jobs/email.py): template rendering,
transport selection, console-transport capture, Resend error classification,
the send_email job's retry mapping, and the enqueue path. Datastore-free —
no Redis/Postgres/network; the Resend transport is exercised over an httpx
MockTransport."""

from __future__ import annotations

import httpx
import pytest
from arq import Retry
from jinja2 import UndefinedError

from app.core import email as email_core
from app.core.config import settings
from app.jobs import email as email_job

ORG_CTX = {
    "inviter_name": "Alex Rivera",
    "org_name": "Acme Talent",
    "accept_url": "https://kandidly.example.com/console?invite=abc123",
    "expiry_note": "This invitation expires in 7 days.",
}
CAND_CTX = {
    "org_name": "Acme Talent",
    "interview_name": "Backend Engineer Screen",
    "interview_url": "https://kandidly.example.com/i/tok123",
    "candidate_name": "Jordan",
    "valid_until": "July 31, 2026",
}
COMPLETED_CTX = {
    "candidate_name": "Jordan Lee",
    "org_name": "Acme Talent",
    "interview_name": "Backend Engineer Screen",
}
CONSOLE_CTX = {
    "inviter_name": "Alex Rivera",
    "landing_url": "https://kandidly.example.com",
}
BRAND_CTX = {
    "brand_name": "Acme Talent",
    "brand_logo_url": "https://cdn.example.com/acme-logo.png",
    "brand_url": "https://acme.example.com",
}


@pytest.fixture(autouse=True)
def _console_default(monkeypatch):
    """Force the auto-selection inputs to a known state (a dev box's
    infra/.env may leak a real Resend key into settings)."""
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "email_transport", "")
    email_core._transports.clear()
    email_core.OUTBOX.clear()


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("template", "context"),
    [
        ("org_invite", ORG_CTX),
        ("console_invite", CONSOLE_CTX),
        ("candidate_invite", CAND_CTX),
        ("interview_completed", COMPLETED_CTX),
    ],
)
def test_render_all_context_vars_in_both_parts(template, context):
    rendered = email_core.render_email(template, context)
    for value in context.values():
        assert value in rendered.html, f"{value!r} missing from html part"
        assert value in rendered.text, f"{value!r} missing from text part"
    # base layout present in both parts (default brand: no brand_* in context)
    assert "Kandidly" in rendered.html and "Kandidly" in rendered.text
    assert "automated message" in rendered.html and "automated message" in rendered.text
    assert "\n" not in rendered.subject and rendered.subject.strip()


def test_subjects():
    assert (
        email_core.render_email("org_invite", ORG_CTX).subject
        == "Alex Rivera invited you to Acme Talent on Kandidly"
    )
    assert (
        email_core.render_email("console_invite", CONSOLE_CTX).subject
        == "Alex Rivera has invited you to Kandidly AI"
    )
    assert (
        email_core.render_email("candidate_invite", CAND_CTX).subject
        == "Acme Talent invited you to interview — Backend Engineer Screen"
    )
    assert (
        email_core.render_email("interview_completed", COMPLETED_CTX).subject
        == "Interview complete — Backend Engineer Screen"
    )


def test_candidate_invite_optional_lines_drop_cleanly():
    """candidate_name and valid_until are optional: without them the greeting
    and validity lines vanish instead of rendering 'Hi ,' / 'valid until .'"""
    ctx = {k: v for k, v in CAND_CTX.items() if k not in ("candidate_name", "valid_until")}
    rendered = email_core.render_email("candidate_invite", ctx)
    for part in (rendered.html, rendered.text):
        assert "Hi " not in part
        assert "valid until" not in part
    assert CAND_CTX["interview_url"] in rendered.html


def test_completed_email_says_someone_will_reach_out():
    rendered = email_core.render_email("interview_completed", COMPLETED_CTX)
    for part in (rendered.html, rendered.text):
        assert "reach out" in part
        assert "review your interview" in part


# --------------------------------------------------------------------------- #
# brand placeholders (upcoming brand integration — base layout accommodates)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("template", "context"),
    [("candidate_invite", CAND_CTX), ("interview_completed", COMPLETED_CTX)],
)
def test_brand_placeholders_render_logo_and_link(template, context):
    rendered = email_core.render_email(template, {**context, **BRAND_CTX})
    assert f'<img src="{BRAND_CTX["brand_logo_url"]}" alt="Acme Talent"' in rendered.html
    assert f'<a href="{BRAND_CTX["brand_url"]}"' in rendered.html
    # branded footer replaces the default Kandidly identity in both parts
    assert "automated message from Acme Talent" in rendered.html
    assert "automated message from Acme Talent" in rendered.text
    assert BRAND_CTX["brand_url"] in rendered.text


def test_brand_name_without_logo_renders_text_header():
    ctx = {**CAND_CTX, "brand_name": "Acme Talent", "brand_url": "https://acme.example.com"}
    rendered = email_core.render_email("candidate_invite", ctx)
    assert "<img" not in rendered.html
    assert ">Acme Talent</span>" in rendered.html


def test_no_brand_context_falls_back_to_kandidly_defaults():
    rendered = email_core.render_email("candidate_invite", CAND_CTX)
    assert "<img" not in rendered.html
    assert ">Kandidly</span>" in rendered.html
    assert "automated message from Kandidly" in rendered.text


def test_html_part_escapes_context_text_part_does_not():
    ctx = {**ORG_CTX, "inviter_name": 'Ana <"Dev"> & Co'}
    rendered = email_core.render_email("org_invite", ctx)
    assert "Ana &lt;&#34;Dev&#34;&gt; &amp; Co" in rendered.html
    assert 'Ana <"Dev"> & Co' in rendered.text


def test_missing_context_var_raises():
    incomplete = {k: v for k, v in ORG_CTX.items() if k != "accept_url"}
    with pytest.raises(UndefinedError):
        email_core.render_email("org_invite", incomplete)


# --------------------------------------------------------------------------- #
# transport selection + console capture
# --------------------------------------------------------------------------- #
def test_transport_defaults_to_console_without_api_key():
    assert isinstance(email_core.get_transport(), email_core.ConsoleTransport)


def test_transport_auto_selects_resend_with_api_key(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    assert isinstance(email_core.get_transport(), email_core.ResendTransport)


def test_explicit_transport_setting_wins(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(settings, "email_transport", "console")
    assert isinstance(email_core.get_transport(), email_core.ConsoleTransport)


async def test_console_transport_captures_rendered_email():
    message_id = await email_core.send(to="dev@example.com", template="org_invite", context=ORG_CTX)
    assert message_id is None
    (captured,) = email_core.OUTBOX
    assert captured["to"] == "dev@example.com"
    assert captured["subject"] == "Alex Rivera invited you to Acme Talent on Kandidly"
    assert ORG_CTX["accept_url"] in captured["html"]
    assert ORG_CTX["accept_url"] in captured["text"]


# --------------------------------------------------------------------------- #
# resend transport error classification
# --------------------------------------------------------------------------- #
def _resend_with_response(status: int, body: dict) -> email_core.ResendTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return email_core.ResendTransport(client=client)


async def test_resend_success_returns_message_id():
    transport = _resend_with_response(200, {"id": "msg_123"})
    rendered = email_core.render_email("org_invite", ORG_CTX)
    assert await transport.send(to="a@b.co", message=rendered) == "msg_123"


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (500, True), (422, False)])
async def test_resend_error_classification(status, retryable):
    transport = _resend_with_response(status, {"message": "nope"})
    rendered = email_core.render_email("org_invite", ORG_CTX)
    with pytest.raises(email_core.EmailSendError) as exc_info:
        await transport.send(to="a@b.co", message=rendered)
    assert exc_info.value.retryable is retryable


# --------------------------------------------------------------------------- #
# send_email job: retry mapping, loud terminal failure, no crash loops
# --------------------------------------------------------------------------- #
def _failing_send(monkeypatch, exc: Exception):
    async def _raise(*, to, template, context):
        raise exc

    monkeypatch.setattr(email_core, "send", _raise)


async def test_job_retries_retryable_failures_with_backoff(monkeypatch):
    _failing_send(monkeypatch, email_core.EmailSendError("resend 503", retryable=True))
    with pytest.raises(Retry) as exc_info:
        await email_job.send_email({"job_try": 1}, "a@b.co", "org_invite", ORG_CTX)
    assert exc_info.value.defer_score == 30_000  # arq stores defer in ms
    with pytest.raises(Retry) as exc_info:
        await email_job.send_email({"job_try": 3}, "a@b.co", "org_invite", ORG_CTX)
    assert exc_info.value.defer_score == 120_000


async def test_job_gives_up_after_max_tries(monkeypatch):
    _failing_send(monkeypatch, email_core.EmailSendError("resend 503", retryable=True))
    # Terminal try: logs and returns instead of raising — arq must not requeue.
    await email_job.send_email({"job_try": email_job.MAX_TRIES}, "a@b.co", "org_invite", ORG_CTX)


async def test_job_never_retries_non_retryable_failures(monkeypatch):
    _failing_send(monkeypatch, email_core.EmailSendError("resend 422", retryable=False))
    await email_job.send_email({"job_try": 1}, "a@b.co", "org_invite", ORG_CTX)


async def test_job_swallows_render_errors(monkeypatch):
    await email_job.send_email({"job_try": 1}, "a@b.co", "org_invite", {})  # missing vars


async def test_job_sends_through_console_transport():
    await email_job.send_email({"job_try": 1}, "cand@example.com", "candidate_invite", CAND_CTX)
    (captured,) = email_core.OUTBOX
    assert captured["to"] == "cand@example.com"


# --------------------------------------------------------------------------- #
# enqueue path
# --------------------------------------------------------------------------- #
async def test_enqueue_email(monkeypatch):
    calls: list[tuple] = []

    async def _record(job, *args, **kwargs):
        calls.append((job, args))

    monkeypatch.setattr(email_job, "enqueue", _record)
    await email_job.enqueue_email("a@b.co", "candidate_invite", CAND_CTX)
    assert calls == [("send_email", ("a@b.co", "candidate_invite", CAND_CTX))]
