"""verify_jwt / mint_app_jwt: the app's own HS256 bearer tokens work in every
env; unsigned dev debug tokens are honored ONLY in env == "dev" (with
AUTH_DEV_MODE on) — prod rejects them regardless of the flag."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt as pyjwt
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import mint_app_jwt, verify_jwt


def _dev_token(user_id, email="dev@x.com", role="admin") -> str:
    payload = {"user_id": str(user_id), "email": email, "role": role}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def test_app_jwt_roundtrip_any_env(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "auth_dev_mode", False)
    user_id, org_id = uuid4(), uuid4()
    token = mint_app_jwt(user_id=user_id, email="a@b.com", role="recruiter", org_id=org_id)
    user = verify_jwt(token)
    assert (user.user_id, user.email, user.role, user.org_id) == (
        user_id,
        "a@b.com",
        "recruiter",
        org_id,
    )


def test_app_jwt_org_id_optional():
    token = mint_app_jwt(user_id=uuid4(), email="c@d.com", role="candidate", org_id=None)
    assert verify_jwt(token).org_id is None


def test_dev_token_accepted_only_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    user_id = uuid4()
    assert verify_jwt(_dev_token(user_id)).user_id == user_id


@pytest.mark.parametrize(
    ("env", "dev_mode"),
    [("prod", True), ("prod", False), ("staging", True), ("dev", False)],
)
def test_dev_token_rejected_outside_dev(monkeypatch, env, dev_mode):
    monkeypatch.setattr(settings, "env", env)
    monkeypatch.setattr(settings, "auth_dev_mode", dev_mode)
    with pytest.raises(AppError) as exc:
        verify_jwt(_dev_token(uuid4()))
    assert exc.value.code == "unauthorized"


def test_tampered_signature_rejected(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "auth_dev_mode", False)
    token = mint_app_jwt(user_id=uuid4(), email="a@b.com", role="admin", org_id=None)
    forged = pyjwt.encode(
        pyjwt.decode(token, options={"verify_signature": False}),
        "some-other-secret-of-sufficient-length-1234",
        algorithm="HS256",
    )
    with pytest.raises(AppError):
        verify_jwt(forged)


def test_expired_app_jwt_rejected(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "auth_dev_mode", False)
    now = datetime.now(UTC)
    token = pyjwt.encode(
        {
            "sub": str(uuid4()),
            "email": "a@b.com",
            "role": "admin",
            "org_id": None,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(AppError):
        verify_jwt(token)


def test_role_claim_required():
    token = pyjwt.encode(
        {"sub": str(uuid4()), "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(AppError) as exc:
        verify_jwt(token)
    assert "claims" in exc.value.message
