"""/api/public/dev-users hands out working bearer tokens, so it must only
exist in dev: the gate requires BOTH AUTH_DEV_MODE and env == "dev" (mirroring
verify_jwt's dev-token gate). Prod always 404s — real logins go through WorkOS
AuthKit."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.public import dev_users
from app.core.config import settings
from app.core.errors import AppError


class _FakeResult:
    def __init__(self, users):
        self._users = users

    def scalars(self):
        return self

    def all(self):
        return self._users


class _FakeDB:
    def __init__(self, users):
        self._users = users

    async def execute(self, stmt):
        return _FakeResult(self._users)


def _users():
    return [
        SimpleNamespace(id=uuid4(), email="admin@x.com", role="admin"),
        SimpleNamespace(id=uuid4(), email="recruiter@x.com", role="recruiter"),
        SimpleNamespace(id=uuid4(), email="cand@x.com", role="candidate"),
    ]


async def test_dev_lists_everyone(monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    out = await dev_users(_FakeDB(_users()))
    assert sorted(u["role"] for u in out) == ["admin", "candidate", "recruiter"]


async def test_prod_404s_even_with_dev_mode_on(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    with pytest.raises(AppError) as exc:
        await dev_users(_FakeDB(_users()))
    assert exc.value.code == "not_found"


async def test_404_outside_auth_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "auth_dev_mode", False)
    with pytest.raises(AppError) as exc:
        await dev_users(_FakeDB(_users()))
    assert exc.value.code == "not_found"
