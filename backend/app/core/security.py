"""App auth tokens (supersedes SPEC §3.6's external-IdP contract). Identity
comes from WorkOS AuthKit (app/api/auth.py), but the bearer token the app
verifies is our OWN HS256 JWT minted at the auth callback — so everything
downstream (deps.py, role guards, logout denylist) never touches WorkOS.
Unsigned dev debug tokens are still accepted, but only in env == "dev"."""

from __future__ import annotations

import json
import secrets
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.errors import AppError

Role = Literal["admin", "recruiter", "candidate"]


@dataclass(frozen=True)
class AuthUser:
    user_id: UUID
    email: str
    role: Role
    org_id: UUID | None = None


def mint_app_jwt(*, user_id: UUID, email: str, role: str, org_id: UUID | None) -> str:
    """Bearer JWT handed to the SPA after the AuthKit callback. Claim shape
    matches what verify_jwt resolves (sub/email/role/org_id)."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "org_id": str(org_id) if org_id else None,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_ttl_s),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_dev_token(token: str) -> dict:
    """Dev debug token: base64url of a JSON payload {user_id,email,role}. Unsigned."""
    padded = token + "=" * (-len(token) % 4)
    return json.loads(urlsafe_b64decode(padded.encode()))


def verify_jwt(token: str) -> AuthUser:
    """Verify a bearer token and return the resolved user. Raises AppError(401)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError as jwt_exc:
        # Unsigned dev tokens (seed picker, API test suite) never parse as a
        # signed JWT; they are honored in dev ONLY — prod rejects them even
        # with AUTH_DEV_MODE accidentally on.
        if not (settings.auth_dev_mode and settings.is_dev):
            raise AppError("unauthorized", "Invalid or expired token") from jwt_exc
        try:
            payload = _decode_dev_token(token)
        except Exception as exc:  # noqa: BLE001
            raise AppError("unauthorized", "Invalid or expired token") from exc

    user_id = payload.get("user_id") or payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")
    org_id = payload.get("org_id")
    if not user_id or role not in ("admin", "recruiter", "candidate"):
        raise AppError("unauthorized", "Token missing required claims")
    return AuthUser(
        user_id=UUID(str(user_id)),
        email=email or "",
        role=role,
        org_id=UUID(str(org_id)) if org_id else None,
    )


def verify_service_token(provided: str | None) -> None:
    """Constant-time check of X-Service-Token (SPEC §12.4)."""
    if not provided or not secrets.compare_digest(provided, settings.service_token):
        raise AppError("unauthorized", "Invalid service token")


# --- logout denylist ---------------------------------------------------------
# Bearer tokens are stateless, so logout is a server-side denylist in Redis
# keyed by token hash. Checks fail open: an unreachable Redis must not take
# every authenticated route down with it.
def _token_key(token: str) -> str:
    from hashlib import sha256

    return f"auth:revoked:{sha256(token.encode()).hexdigest()}"


async def revoke_token(token: str) -> None:
    from app.core import cache

    await cache.set_json(
        _token_key(token), {"revoked": True}, ttl=settings.auth_revoked_token_ttl_s
    )


async def is_token_revoked(token: str) -> bool:
    from app.core import cache

    try:
        return await cache.get_json(_token_key(token)) is not None
    except Exception:  # noqa: BLE001 — fail open when Redis is unavailable
        return False
