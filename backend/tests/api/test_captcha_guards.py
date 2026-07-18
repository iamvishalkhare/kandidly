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


# --- score thresholds ------------------------------------------------------- #
# Real first-visit humans commonly score 0.3 on the cold landing load (observed
# in prod 2026-07-18), so the landing pair takes a lower bar than in-flow
# actions. siteverify is faked here — thresholds, not Google, are under test.


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


async def test_landing_admits_cold_load_scores(
    client, enforce_captcha, fake_siteverify, monkeypatch
):
    monkeypatch.setattr(settings, "recaptcha_min_score", 0.5)
    monkeypatch.setattr(settings, "recaptcha_min_score_landing", 0.2)
    fake_siteverify["payload"] = {"success": True, "score": 0.3, "action": "link_resolve"}
    r = await client.get("/api/public/i/not-a-real-token", headers={"X-Recaptcha-Token": "tok"})
    assert r.status_code == 200  # 0.3 clears the landing bar even with global at 0.5


async def test_in_flow_actions_keep_the_stricter_bar(
    client, candidate_headers, enforce_captcha, fake_siteverify, monkeypatch
):
    monkeypatch.setattr(settings, "recaptcha_min_score", 0.5)
    fake_siteverify["payload"] = {"success": True, "score": 0.3, "action": "form_submit"}
    r = await client.post(
        "/api/candidate/applications/00000000-0000-0000-0000-000000000000/form/submit",
        headers={**candidate_headers, "X-Recaptcha-Token": "tok"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["score"] == 0.3
