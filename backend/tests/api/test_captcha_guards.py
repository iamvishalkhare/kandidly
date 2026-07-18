"""reCAPTCHA v3 guard placement + threshold.

Product decision (2026-07-18): the landing endpoints (resolve + claim) are
deliberately NOT captcha-guarded — v3 scores cold first-visit page loads so
low that real candidates were blocked in prod. Only the costly in-flow step
(form/submit) keeps the gate; these tests pin that placement both ways.

The suite conftest blanks the secret so every other test runs fail-open;
enforcement is flipped on per-test here. A missing/empty token raises before
any siteverify network call (app/core/captcha.py), so the fail-closed path
needs no mocking; the threshold tests fake siteverify.
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


@pytest.fixture()
def fake_siteverify(monkeypatch):
    from app.core import captcha as captcha_mod

    state: dict = {"payload": {}}

    class _Resp:
        def json(self):
            return state["payload"]

    class _Client:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None):
            return _Resp()

    monkeypatch.setattr(captcha_mod.httpx, "AsyncClient", _Client)
    return state


# --- landing endpoints: no captcha, even when enforcement is on ------------- #


async def test_resolve_has_no_captcha(client, enforce_captcha):
    r = await client.get("/api/public/i/not-a-real-token")
    assert r.status_code == 200
    assert r.json()["status_ok"] is False


async def test_claim_has_no_captcha(client, candidate_headers, enforce_captcha):
    r = await client.post("/api/candidate/i/not-a-real-token/claim", headers=candidate_headers)
    # The unknown token is rejected by link validation, never by captcha.
    assert r.json().get("code") != "captcha_failed"


# --- form/submit keeps the gate --------------------------------------------- #


async def test_form_submit_fails_closed_without_token(client, candidate_headers, enforce_captcha):
    # The dependency runs before the handler, so application state is moot.
    r = await client.post(
        "/api/candidate/applications/00000000-0000-0000-0000-000000000000/form/submit",
        headers=candidate_headers,
    )
    assert r.status_code == 403
    assert r.json()["code"] == "captcha_failed"


async def test_form_submit_admits_observed_human_score(
    client, candidate_headers, enforce_captcha, fake_siteverify, monkeypatch
):
    # Real humans scored 0.3 in prod (2026-07-18) — the threshold must admit it.
    monkeypatch.setattr(settings, "recaptcha_min_score", 0.3)
    fake_siteverify["payload"] = {"success": True, "score": 0.3, "action": "form_submit"}
    r = await client.post(
        "/api/candidate/applications/00000000-0000-0000-0000-000000000000/form/submit",
        headers={**candidate_headers, "X-Recaptcha-Token": "tok"},
    )
    assert r.json().get("code") != "captcha_failed"  # past the gate (app itself 404s)


async def test_form_submit_blocks_automation_score(
    client, candidate_headers, enforce_captcha, fake_siteverify, monkeypatch
):
    # Headless automation scored 0.1 — must stay below the bar.
    monkeypatch.setattr(settings, "recaptcha_min_score", 0.3)
    fake_siteverify["payload"] = {"success": True, "score": 0.1, "action": "form_submit"}
    r = await client.post(
        "/api/candidate/applications/00000000-0000-0000-0000-000000000000/form/submit",
        headers={**candidate_headers, "X-Recaptcha-Token": "tok"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["score"] == 0.1
