"""Invite-only console access (domain/access.py + /api/admin/console/allowlist):
the WorkOS console-intent login gate (blocked / allowlisted / operator-hardcode
paths, no user row leakage on rejection, candidate intent ungated) and the
operator-only allowlist management API. Reuses the WorkOS stub + login drivers
from test_workos_auth."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from tests.api.conftest import auth, mint_token
from tests.api.test_workos_auth import (
    _allow,
    _fragment,
    _login,
    _StubWorkOS,
    _token_from,
    _wuser,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def workos(monkeypatch):
    import app.api.auth as auth_api

    stub = _StubWorkOS()
    monkeypatch.setattr(auth_api, "get_client", lambda: stub)
    return stub


async def _user_count(email: str) -> int:
    from app.db.models import User
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        return (
            await db.execute(
                select(func.count(User.id)).where(func.lower(User.email) == email.lower())
            )
        ).scalar_one()


@pytest_asyncio.fixture(loop_scope="session")
async def operator_headers():
    """Bearer for the hardcoded operator account (created directly — the
    operator needs no allowlist row, so no seeded fixture exists for it)."""
    from app.core.ids import new_id
    from app.db.models import User
    from app.db.session import SessionLocal
    from app.domain.access import OPERATOR_EMAIL

    async with SessionLocal() as db:
        row = (
            await db.execute(select(User).where(User.email == OPERATOR_EMAIL))
        ).scalar_one_or_none()
        if row is None:
            row = User(id=new_id(), email=OPERATOR_EMAIL, role="admin", status="active")
            db.add(row)
            await db.commit()
        user_id = row.id
    return auth(mint_token(user_id, OPERATOR_EMAIL, "admin"))


# --------------------------------------------------------------------------- #
# login gate
# --------------------------------------------------------------------------- #
async def test_console_login_blocked_when_not_allowlisted(client, workos):
    email = f"stranger-{uuid.uuid4().hex[:8]}@mail.dev"
    frag = _fragment(await _login(client, workos, _wuser(email)))
    assert frag == {"error": "not_allowlisted"}
    # Rejected before JIT provisioning — no user (and thus no org) was created.
    assert await _user_count(email) == 0


async def test_operator_email_always_allowed(client, workos, operator_headers):
    from app.domain.access import OPERATOR_EMAIL

    token = await _token_from(await _login(client, workos, _wuser(OPERATOR_EMAIL)))
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["email"].lower() == OPERATOR_EMAIL


async def test_allowlisted_email_can_login(client, workos):
    email = f"guest-{uuid.uuid4().hex[:8]}@mail.dev"
    await _allow(email)
    token = await _token_from(await _login(client, workos, _wuser(email)))
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200


async def test_candidate_intent_is_not_gated(client, workos):
    email = f"cand-open-{uuid.uuid4().hex[:8]}@mail.dev"
    token = await _token_from(await _login(client, workos, _wuser(email), intent="candidate"))
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200


# --------------------------------------------------------------------------- #
# management API (operator-only)
# --------------------------------------------------------------------------- #
async def test_allowlist_api_forbidden_for_other_console_users(client, admin_headers):
    r = await client.get("/api/admin/console/allowlist", headers=admin_headers)
    assert r.status_code == 403
    r = await client.post(
        "/api/admin/console/allowlist", json={"email": "x@y.dev"}, headers=admin_headers
    )
    assert r.status_code == 403
    r = await client.delete(f"/api/admin/console/allowlist/{uuid.uuid4()}", headers=admin_headers)
    assert r.status_code == 403


async def test_allowlist_add_list_remove_roundtrip(client, workos, operator_headers):
    from app.domain.access import OPERATOR_EMAIL

    email = f"invitee-{uuid.uuid4().hex[:8]}@mail.dev"

    # Add (mixed case in → stored normalized), then the email can sign in.
    r = await client.post(
        "/api/admin/console/allowlist",
        json={"email": f"  {email.upper()} "},
        headers=operator_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["entry"]["email"] == email
    entry_id = body["entry"]["id"]

    r = await client.get("/api/admin/console/allowlist", headers=operator_headers)
    assert r.status_code == 200
    listing = r.json()
    assert listing["operator_email"] == OPERATOR_EMAIL
    assert email in [e["email"] for e in listing["items"]]

    token = await _token_from(await _login(client, workos, _wuser(email)))
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200

    # Re-adding is idempotent.
    r = await client.post(
        "/api/admin/console/allowlist", json={"email": email}, headers=operator_headers
    )
    assert r.status_code == 200 and r.json()["created"] is False

    # Remove → the next sign-in is blocked again.
    r = await client.delete(f"/api/admin/console/allowlist/{entry_id}", headers=operator_headers)
    assert r.status_code == 200
    frag = _fragment(await _login(client, workos, _wuser(email)))
    assert frag == {"error": "not_allowlisted"}


async def test_allowlist_rejects_invalid_email(client, operator_headers):
    r = await client.post(
        "/api/admin/console/allowlist", json={"email": "not-an-email"}, headers=operator_headers
    )
    assert r.status_code == 422


async def test_allowlist_remove_unknown_entry_404s(client, operator_headers):
    r = await client.delete(
        f"/api/admin/console/allowlist/{uuid.uuid4()}", headers=operator_headers
    )
    assert r.status_code == 404
