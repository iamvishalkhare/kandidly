"""POST /api/admin/console/email-test — operator-gated smoke sender. Same
hardcoded-email gate as interview deletion; sends synchronously so the
response carries the transport outcome."""

from __future__ import annotations

import pytest

from app.core.ids import new_id
from tests.api.conftest import auth, mint_token

pytestmark = pytest.mark.asyncio(loop_scope="session")

OPERATOR_EMAIL = "vishalkhare39@gmail.com"


def _operator_headers() -> dict[str, str]:
    return auth(mint_token(new_id(), OPERATOR_EMAIL, "admin"))


@pytest.fixture(autouse=True)
def _console_transport(monkeypatch):
    """Force the console transport (a dev box's infra/.env may carry a real
    Resend key) and give each test a clean outbox."""
    from app.core import email as email_core
    from app.core.config import settings

    monkeypatch.setattr(settings, "email_transport", "console")
    email_core._transports.clear()
    email_core.OUTBOX.clear()


async def test_forbidden_for_non_operator_admin(client, admin_headers):
    from app.core import email as email_core

    r = await client.post(
        "/api/admin/console/email-test",
        json={"template": "org_invite", "to": "someone@example.com"},
        headers=admin_headers,
    )
    assert r.status_code == 403
    assert not email_core.OUTBOX


async def test_rejects_unknown_template(client):
    r = await client.post(
        "/api/admin/console/email-test",
        json={"template": "password_reset", "to": "someone@example.com"},
        headers=_operator_headers(),
    )
    assert r.status_code == 422


async def test_operator_sends_sample_email(client):
    from app.core import email as email_core

    r = await client.post(
        "/api/admin/console/email-test",
        json={"template": "candidate_invite", "to": "me@example.com"},
        headers=_operator_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transport"] == "ConsoleTransport"
    assert body["message_id"] is None
    assert body["subject"] == "Acme Talent invited you to interview — Backend Engineer Screen"

    (captured,) = email_core.OUTBOX
    assert captured["to"] == "me@example.com"
    assert "/i/smoke-test-token" in captured["html"]
    assert "/i/smoke-test-token" in captured["text"]


async def test_operator_sends_completed_sample(client):
    from app.core import email as email_core

    r = await client.post(
        "/api/admin/console/email-test",
        json={"template": "interview_completed", "to": "me@example.com"},
        headers=_operator_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["subject"] == "Interview complete — Backend Engineer Screen"
    (captured,) = email_core.OUTBOX
    assert "reach out" in captured["text"]
