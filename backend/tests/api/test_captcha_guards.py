"""reCAPTCHA v3 guards on the public landing endpoints (resolve + claim).

The suite conftest blanks the secret so every other test runs fail-open;
these tests flip enforcement on per-test. A missing/empty token raises
before any siteverify network call (app/core/captcha.py), so no mocking
of Google is needed for the fail-closed path.
"""

from __future__ import annotations

import pytest

from app.core.config import settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture()
def enforce_captcha():
    settings.recaptcha_secret_key = "test-secret"
    yield
    settings.recaptcha_secret_key = ""


async def test_resolve_fails_closed_without_token(client, enforce_captcha):
    r = await client.get("/api/public/i/whatever-token")
    assert r.status_code == 403
    assert r.json()["code"] == "captcha_failed"


async def test_claim_fails_closed_without_token(client, candidate_headers, enforce_captcha):
    r = await client.post("/api/candidate/i/whatever-token/claim", headers=candidate_headers)
    assert r.status_code == 403
    assert r.json()["code"] == "captcha_failed"


async def test_resolve_fails_open_when_unconfigured(client):
    # conftest blanks the secret — no token required, endpoint behaves normally.
    r = await client.get("/api/public/i/not-a-real-token")
    assert r.status_code == 200
    assert r.json()["status_ok"] is False


async def test_form_submit_still_guarded(
    client, admin_headers, candidate_headers, high_requisition_cap, enforce_captcha
):
    # The pre-existing guard (regression): submit without a token is rejected
    # regardless of application state — the dependency runs before the handler.
    r = await client.post(
        "/api/candidate/applications/00000000-0000-0000-0000-000000000000/form/submit",
        headers=candidate_headers,
    )
    assert r.status_code == 403
    assert r.json()["code"] == "captcha_failed"
