"""Auth routes: WorkOS AuthKit redirect flow + session end.

Login: `GET /login` stores a one-time CSRF `state` (Redis, 10 min) alongside
the caller's intent (console vs candidate) and safe return path, then redirects
to the AuthKit hosted UI. `GET /callback` exchanges the code, JIT-provisions
our User row (domain/provisioning.py), mints the app's own HS256 JWT, and
hands it to the SPA.

Token handoff: redirect to `{base_url_web}/auth/callback?next=<path>#token=<jwt>`.
The JWT rides in the URL *fragment* deliberately — fragments never leave the
browser (no server logs, no Referer leakage), and the SPA reads + clears it
immediately. Simpler than a second exchange-code hop and safe enough given the
token already only lives in localStorage. All failures land on
`#error=<code>`: pre-auth ones (auth_failed | state_mismatch) directly, and
rejections of an authenticated account (not_allowlisted | account_suspended |
account_invited | not_console_account | not_candidate_account) after the
WorkOS session is revoked server-side — see _reject for why it must NOT be
the logout-URL browser bounce.

Console sign-in is invite-only: the email must pass domain/access.py's
allowlist check *before* JIT provisioning, so uninvited sign-ins never
create user/org rows. An allowlisted email that already exists as a
*candidate* account is promoted to a console account on its first
console-intent login (domain/provisioning.py). Candidate sign-ins are not
gated.

Logout denylists the presented bearer in Redis (kills our own session) *and*
ends the WorkOS AuthKit hosted session (kills its SSO cookie) — skipping the
latter would let a subsequent `/login` silently re-authenticate the same
account without ever prompting, since AuthKit's own cookie would still be
live in the browser.
"""

from __future__ import annotations

import secrets
from urllib.parse import quote

import jwt as pyjwt
from fastapi import APIRouter, Depends, Header
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.ratelimit import rate_limit
from app.core.security import AuthUser, mint_app_jwt, revoke_token
from app.core.workos_client import get_client
from app.db.models import User
from app.domain.access import console_login_allowed
from app.domain.audit import record_audit
from app.domain.provisioning import promote_candidate_to_console, provision_workos_user
from app.schemas.api import MeOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

_STATE_TTL_S = 600


def _safe_return_to(raw: str | None) -> str:
    """Only same-app absolute paths — never a full URL (open-redirect guard)."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/"


def _workos_session_id(access_token: str | None) -> str | None:
    """Pull the `sid` claim off WorkOS's access token. Not verified — WorkOS
    already vouched for this token during the code exchange; we only need the
    session id to ask WorkOS to end that same session at logout."""
    if not access_token:
        return None
    try:
        payload = pyjwt.decode(access_token, options={"verify_signature": False})
    except pyjwt.InvalidTokenError:
        return None
    sid = payload.get("sid")
    return str(sid) if sid else None


@router.get("/login", dependencies=[rate_limit("auth_login", 30, by="ip")])
async def login(intent: str = "console", return_to: str | None = None) -> RedirectResponse:
    intent = "candidate" if intent == "candidate" else "console"
    state = secrets.token_urlsafe(24)
    await cache.set_json(
        f"auth:state:{state}",
        {"intent": intent, "return_to": _safe_return_to(return_to)},
        ttl=_STATE_TTL_S,
    )
    url = get_client().user_management.get_authorization_url(
        provider="authkit",
        redirect_uri=settings.workos_redirect_uri,
        state=state,
    )
    return RedirectResponse(url, status_code=302)


def _spa_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.base_url_web}/auth/callback#error={code}", status_code=302)


def _reject(code: str, wos_sid: str | None) -> RedirectResponse:
    """Rejection of an *authenticated* sign-in (not allowlisted, suspended,
    wrong account kind): revoke the WorkOS session server-side — so AuthKit's
    SSO cookie can't silently re-authenticate the same rejected account on the
    next /login — then land directly on the SPA error screen.

    Deliberately NOT a browser bounce through WorkOS's logout URL: WorkOS only
    honors a logout `return_to` that is pre-registered as a sign-out redirect
    in its dashboard, and silently falls back to the default redirect (the
    landing page) otherwise — which swallowed every rejection screen in prod
    (2026-07-20). If server-side revocation ever proves not to end the hosted
    session, the fallback fix is registering {base}/auth/callback as a
    sign-out redirect and restoring the bounce."""
    if wos_sid:
        try:
            get_client().user_management.revoke_session(session_id=wos_sid)
        except Exception:  # noqa: BLE001 — the error screen must still render
            pass
    return _spa_error(code)


@router.get("/callback", dependencies=[rate_limit("auth_callback", 30, by="ip")])
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error or not code or not state:
        return _spa_error("auth_failed")

    st = await cache.get_json(f"auth:state:{state}")
    if st is None:
        return _spa_error("state_mismatch")
    await cache.delete(f"auth:state:{state}")  # one-time use

    try:
        auth_resp = get_client().user_management.authenticate_with_code(code=code)
    except Exception:  # noqa: BLE001 — expired/reused codes must not 500
        return _spa_error("auth_failed")

    wos_sid = _workos_session_id(getattr(auth_resp, "access_token", None))
    intent = st.get("intent", "console")
    if intent == "console" and not await console_login_allowed(db, auth_resp.user.email):
        return _reject("not_allowlisted", wos_sid)
    result = await provision_workos_user(db, auth_resp.user, intent)
    user = result.user

    if user.status == "suspended":
        return _reject("account_suspended", wos_sid)
    if user.status == "invited":
        return _reject("account_invited", wos_sid)
    if intent == "console" and user.role == "candidate":
        # The allowlist gate above already passed: the operator explicitly
        # granted this email console access, so an account that only exists
        # because it once took an interview gets promoted instead of bounced.
        await promote_candidate_to_console(db, user, auth_resp.user)
        await record_audit(
            db,
            actor_id=user.id,
            action="user.console_promoted",
            entity_type="user",
            entity_id=user.id,
        )
    if intent == "console" and user.role not in ("admin", "recruiter"):
        return _reject("not_console_account", wos_sid)
    if intent == "candidate" and user.role != "candidate":
        return _reject("not_candidate_account", wos_sid)
    token = mint_app_jwt(
        user_id=user.id,
        email=user.email,
        role=user.role,
        org_id=user.org_id,
        workos_session_id=wos_sid,
    )
    await record_audit(
        db,
        actor_id=user.id,
        action="user.signup" if result.created else "user.login",
        entity_type="user",
        entity_id=user.id,
    )
    next_q = quote(st.get("return_to", "/"), safe="")
    return RedirectResponse(
        f"{settings.base_url_web}/auth/callback?next={next_q}#token={token}",
        status_code=302,
    )


@router.get("/me", response_model=MeOut)
async def me(
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeOut:
    """Profile for the bearer — the SPA calls this from /auth/callback to
    populate its auth store (the JWT itself is treated as opaque)."""
    row = await db.get(User, user.user_id)
    return MeOut(
        id=user.user_id,
        email=row.email if row else user.email,
        role=row.role if row else user.role,
        org_id=(row.org_id if row else None) or user.org_id,
        display_name=row.display_name if row else None,
        avatar_url=row.avatar_url if row else None,
    )


@router.post("/logout")
async def logout(
    return_to: str | None = None,
    user: AuthUser = Depends(get_current_user),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = authorization.split(" ", 1)[1].strip() if authorization else ""
    if token:
        await revoke_token(token)
    await record_audit(
        db,
        actor_id=user.user_id,
        action="user.logout",
        entity_type="user",
        entity_id=user.user_id,
    )
    logout_url = None
    if user.workos_session_id:
        try:
            logout_url = get_client().user_management.get_logout_url(
                session_id=user.workos_session_id,
                return_to=f"{settings.base_url_web}{_safe_return_to(return_to)}",
            )
        except Exception:  # noqa: BLE001 — app-side logout above already happened
            logout_url = None
    return {"ok": True, "logout_url": logout_url}
