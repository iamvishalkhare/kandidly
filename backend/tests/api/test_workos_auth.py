"""WorkOS AuthKit login flow against the real app (WorkOS SDK stubbed):
JIT provisioning (new console signup → own fresh org; email-link of seeded
users; repeat login), candidate-intent provisioning + personal-invite email
matching, status/intent error redirects, state CSRF, and the app-JWT lifecycle
(me + logout denylist). Dev-token env gating is exercised here too since the
suite runs with AUTH_DEV_MODE=true.

Console sign-in is invite-only (domain/access.py), so every console-intent
login here allowlists its email first via `_allow`; the gate itself is covered
in test_console_allowlist.py."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, unquote, urlsplit

import jwt
import pytest
from sqlalchemy import func, select

import app.api.auth as auth_api
from tests.api.conftest import auth, deploy_requisition, mint_token

pytestmark = pytest.mark.asyncio(loop_scope="session")


# --------------------------------------------------------------------------- #
# WorkOS stub
# --------------------------------------------------------------------------- #
def _wuser(email: str, *, workos_id: str | None = None, first=None, last=None, picture=None):
    return SimpleNamespace(
        id=workos_id or f"user_{uuid.uuid4().hex[:12]}",
        email=email,
        first_name=first,
        last_name=last,
        profile_picture_url=picture,
    )


class _StubWorkOS:
    """Mimics the WorkOSClient.user_management calls the backend makes."""

    def __init__(self):
        self.codes: dict[str, object] = {}
        self.logout_urls: list[dict] = []  # records of get_logout_url() calls
        self.user_management = SimpleNamespace(
            get_authorization_url=self._authorize_url,
            authenticate_with_code=self._authenticate,
            get_logout_url=self._logout_url,
        )

    def _authorize_url(self, *, provider, redirect_uri, state):
        assert provider == "authkit"
        return (
            f"https://auth.workos.test/authorize?redirect_uri={quote(redirect_uri)}&state={state}"
        )

    def _authenticate(self, *, code):
        wuser = self.codes[code]  # KeyError → route's auth_failed path
        # Real WorkOS access tokens are a JWT carrying a `sid` (session id)
        # claim; the app decodes it unverified just to learn the session id.
        access_token = jwt.encode(
            {"sid": f"session_{wuser.id}"},
            "unused-signing-key-for-tests-only-32b",
            algorithm="HS256",
        )
        return SimpleNamespace(user=wuser, access_token=access_token)

    def _logout_url(self, *, session_id, return_to=None):
        self.logout_urls.append({"session_id": session_id, "return_to": return_to})
        rt = quote(return_to or "")
        return f"https://auth.workos.test/sessions/logout?session_id={session_id}&return_to={rt}"


@pytest.fixture
def workos(monkeypatch):
    stub = _StubWorkOS()
    monkeypatch.setattr(auth_api, "get_client", lambda: stub)
    return stub


async def _allow(email: str) -> None:
    """Put an email on the console allowlist directly (idempotent) — these
    tests exercise the login flow, not the operator management API."""
    from app.core.ids import new_id
    from app.db.models import ConsoleAllowlistEntry, User
    from app.db.session import SessionLocal

    email = email.strip().lower()
    async with SessionLocal() as db:
        existing = (
            await db.execute(
                select(ConsoleAllowlistEntry.id).where(ConsoleAllowlistEntry.email == email)
            )
        ).scalar_one_or_none()
        if existing is None:
            adder = (await db.execute(select(User.id).limit(1))).scalar_one()
            db.add(ConsoleAllowlistEntry(id=new_id(), email=email, added_by=adder))
            await db.commit()


async def _login(client, workos, wuser, *, intent="console", return_to="/console"):
    """Drive login → callback; returns the callback redirect Location."""
    r = await client.get(f"/api/auth/login?intent={intent}&return_to={quote(return_to, safe='')}")
    assert r.status_code == 302
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    code = f"code_{uuid.uuid4().hex[:10]}"
    workos.codes[code] = wuser
    r2 = await client.get(f"/api/auth/callback?code={code}&state={state}")
    assert r2.status_code == 302
    return r2.headers["location"]


def _fragment(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(location).fragment).items()}


async def _token_from(location: str) -> str:
    frag = _fragment(location)
    assert "error" not in frag, f"unexpected error redirect: {frag}"
    return frag["token"]


async def _me(client, token: str) -> dict:
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def _default_org_id():
    from app.core.config import settings
    from app.db.models import Organization
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        return (
            await db.execute(
                select(Organization.id).where(Organization.slug == settings.default_org_slug)
            )
        ).scalar_one()


# --------------------------------------------------------------------------- #
# login leg
# --------------------------------------------------------------------------- #
async def test_login_redirects_to_authkit_with_state(client, workos):
    r = await client.get("/api/auth/login?intent=console&return_to=/console")
    assert r.status_code == 302
    url = urlsplit(r.headers["location"])
    assert url.netloc == "auth.workos.test"
    assert parse_qs(url.query)["state"][0]


# --------------------------------------------------------------------------- #
# JIT provisioning
# --------------------------------------------------------------------------- #
async def test_new_console_signup_gets_own_fresh_org(client, workos):
    from app.db.models import Organization, User
    from app.db.session import SessionLocal

    email = f"founder-{uuid.uuid4().hex[:8]}@newco.dev"
    await _allow(email)
    location = await _login(
        client, workos, _wuser(email, first="Nia", last="Founder", picture="https://img/x.png")
    )
    assert unquote(parse_qs(urlsplit(location).query)["next"][0]) == "/console"
    token = await _token_from(location)

    me = await _me(client, token)
    assert me["role"] == "admin"
    assert me["display_name"] == "Nia Founder"
    assert me["avatar_url"] == "https://img/x.png"
    assert me["org_id"] is not None
    assert uuid.UUID(me["org_id"]) != await _default_org_id()

    async with SessionLocal() as db:
        org = await db.get(Organization, uuid.UUID(me["org_id"]))
        row = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one()
    assert org is not None and "Nia Founder" in org.name
    assert row.org_id == org.id and row.workos_user_id

    # The minted JWT drives the console like any staff token.
    r = await client.get("/api/admin/console/me", headers=auth(token))
    assert r.status_code == 200, r.text


async def test_email_link_attaches_workos_id_to_seeded_admin(client, workos):
    from app.db.models import User
    from app.db.session import SessionLocal

    workos_id = f"user_{uuid.uuid4().hex[:12]}"
    await _allow("admin@kandidly.dev")
    location = await _login(client, workos, _wuser("admin@kandidly.dev", workos_id=workos_id))
    token = await _token_from(location)

    me = await _me(client, token)
    assert me["role"] == "admin"
    assert uuid.UUID(me["org_id"]) == await _default_org_id()  # org untouched

    async with SessionLocal() as db:
        row = (
            await db.execute(select(User).where(User.email == "admin@kandidly.dev"))
        ).scalar_one()
    assert row.workos_user_id == workos_id

    # Sees the org's existing data (seeded requisitions).
    r = await client.get("/api/admin/console/requisitions", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()) > 0


async def test_repeat_login_reuses_user_and_org(client, workos):
    from app.db.models import Organization
    from app.db.session import SessionLocal

    wuser = _wuser(f"repeat-{uuid.uuid4().hex[:8]}@newco.dev")
    await _allow(wuser.email)
    first = await _me(client, await _token_from(await _login(client, workos, wuser)))

    async with SessionLocal() as db:
        orgs_before = (await db.execute(select(func.count(Organization.id)))).scalar_one()

    second = await _me(client, await _token_from(await _login(client, workos, wuser)))
    assert second["id"] == first["id"]
    assert second["org_id"] == first["org_id"]

    async with SessionLocal() as db:
        orgs_after = (await db.execute(select(func.count(Organization.id)))).scalar_one()
    assert orgs_after == orgs_before


async def test_fresh_org_is_isolated_from_seeded_data(client, workos):
    """Open signup makes tenant isolation load-bearing: a brand-new org's
    console must see nothing of the seeded org, and its ids must 404."""
    from app.db.models import Interview, Requisition
    from app.db.session import SessionLocal

    email = f"iso-{uuid.uuid4().hex[:8]}@newco.dev"
    await _allow(email)
    token = await _token_from(await _login(client, workos, _wuser(email)))

    r = await client.get("/api/admin/console/interviews", headers=auth(token))
    assert r.status_code == 200 and r.json() == []

    dash = (await client.get("/api/admin/console/dashboard", headers=auth(token))).json()
    assert dash["completed_total"] == 0
    assert dash["active_requisitions"] == 0
    assert dash["recent_interviews"] == []

    async with SessionLocal() as db:
        foreign_req = (await db.execute(select(Requisition.id).limit(1))).scalar_one_or_none()
        foreign_interview = (await db.execute(select(Interview.id).limit(1))).scalar_one_or_none()
    assert foreign_req is not None, "seed should provide requisitions"
    r = await client.get(f"/api/admin/console/requisitions/{foreign_req}", headers=auth(token))
    assert r.status_code == 404
    if foreign_interview:
        r = await client.get(
            f"/api/admin/console/interviews/{foreign_interview}", headers=auth(token)
        )
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# candidate intent
# --------------------------------------------------------------------------- #
async def test_candidate_signup_is_orgless_and_can_claim(
    client, workos, admin_headers, high_requisition_cap
):
    req = await deploy_requisition(client, admin_headers, deploy=True)
    return_to = f"/i/{req['invite_token']}?autostart=1"
    location = await _login(
        client,
        workos,
        _wuser(f"cand-{uuid.uuid4().hex[:8]}@mail.dev"),
        intent="candidate",
        return_to=return_to,
    )
    assert unquote(parse_qs(urlsplit(location).query)["next"][0]) == return_to
    token = await _token_from(location)

    me = await _me(client, token)
    assert me["role"] == "candidate"
    assert me["org_id"] is None

    r = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "registered"


async def test_personal_invite_requires_matching_email(
    client, workos, admin_headers, high_requisition_cap
):
    req = await deploy_requisition(client, admin_headers, deploy=True)
    invited_email = f"invited-{uuid.uuid4().hex[:8]}@mail.dev"
    r = await client.post(
        f"/api/admin/requisitions/{req['id']}/links",
        json={"kind": "personal", "email": invited_email},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    personal_token = r.json()["token"]

    wrong = await _token_from(
        await _login(
            client, workos, _wuser(f"other-{uuid.uuid4().hex[:8]}@mail.dev"), intent="candidate"
        )
    )
    r = await client.post(f"/api/candidate/i/{personal_token}/claim", headers=auth(wrong))
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "email_mismatch"

    right = await _token_from(
        await _login(client, workos, _wuser(invited_email), intent="candidate")
    )
    r = await client.post(f"/api/candidate/i/{personal_token}/claim", headers=auth(right))
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# error redirects
# --------------------------------------------------------------------------- #
async def _set_status(email: str, status: str) -> None:
    from app.db.models import User
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        row = (await db.execute(select(User).where(User.email == email))).scalar_one()
        row.status = status
        await db.commit()


@pytest.mark.parametrize("status", ["suspended", "invited"])
async def test_bad_status_redirects_with_error(client, workos, status):
    wuser = _wuser(f"{status}-{uuid.uuid4().hex[:8]}@mail.dev")
    await _allow(wuser.email)
    await _token_from(await _login(client, workos, wuser))  # provision active
    await _set_status(wuser.email, status)

    frag = _fragment(await _login(client, workos, wuser))
    assert frag == {"error": f"account_{status}"}


async def test_console_intent_rejects_candidate_account(client, workos, candidate):
    # Allowlisted so the invite-only gate (which runs first) doesn't mask the
    # role check: an allowlisted email that belongs to a candidate account
    # still can't open the console.
    await _allow(candidate.email)
    frag = _fragment(await _login(client, workos, _wuser(candidate.email), intent="console"))
    assert frag == {"error": "not_console_account"}


async def test_candidate_intent_rejects_staff_account(client, workos):
    frag = _fragment(await _login(client, workos, _wuser("admin@kandidly.dev"), intent="candidate"))
    assert frag == {"error": "not_candidate_account"}


async def test_unknown_state_rejected(client, workos):
    r = await client.get("/api/auth/callback?code=whatever&state=not-a-real-state")
    assert r.status_code == 302
    assert _fragment(r.headers["location"]) == {"error": "state_mismatch"}


async def test_bad_code_fails_cleanly(client, workos):
    r = await client.get("/api/auth/login?intent=console&return_to=/console")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    r2 = await client.get(f"/api/auth/callback?code=never-issued&state={state}")
    assert _fragment(r2.headers["location"]) == {"error": "auth_failed"}


async def test_open_redirect_blocked(client, workos):
    email = f"redir-{uuid.uuid4().hex[:8]}@x.dev"
    await _allow(email)
    location = await _login(
        client,
        workos,
        _wuser(email),
        return_to="https://evil.example/phish",
    )
    assert unquote(parse_qs(urlsplit(location).query)["next"][0]) == "/"


# --------------------------------------------------------------------------- #
# app-JWT lifecycle
# --------------------------------------------------------------------------- #
async def test_minted_jwt_logout_denylist(client, workos):
    email = f"bye-{uuid.uuid4().hex[:8]}@x.dev"
    await _allow(email)
    token = await _token_from(await _login(client, workos, _wuser(email)))
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200

    r = await client.post("/api/auth/logout", headers=auth(token))
    assert r.status_code == 200

    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 401
    assert "logged out" in r.json()["message"]


async def test_logout_ends_workos_session_too(client, workos):
    """Logout must return a WorkOS session-logout URL, not just denylist our
    own JWT — otherwise AuthKit's SSO cookie survives and a later /login
    silently re-authenticates the same account without prompting."""
    wuser = _wuser(f"bye2-{uuid.uuid4().hex[:8]}@x.dev")
    await _allow(wuser.email)
    token = await _token_from(await _login(client, workos, wuser))

    r = await client.post("/api/auth/logout?return_to=/console", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["logout_url"], "expected a WorkOS logout_url to end the SSO session"

    url = urlsplit(body["logout_url"])
    assert url.netloc == "auth.workos.test"
    qs = parse_qs(url.query)
    assert qs["session_id"][0] == f"session_{wuser.id}"
    assert unquote(qs["return_to"][0]) == "http://localhost:5173/console"


async def test_dev_token_rejected_outside_dev_env(client, monkeypatch, candidate):
    from app.core.config import settings

    token = mint_token(candidate.id, candidate.email, "candidate")
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200

    monkeypatch.setattr(settings, "env", "prod")
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 401
