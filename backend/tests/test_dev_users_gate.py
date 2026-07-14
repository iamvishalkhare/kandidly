"""TEMPORARY prod stopgap (infra/Caddyfile.prod): /api/public/dev-users must
hide staff tokens unless the edge proxy asserts X-Console-Gate — under
AUTH_DEV_MODE those tokens are working console credentials. Candidate accounts
stay listed (the /i/<token> landing picker needs them). Delete this file
alongside the dev-token scheme when WorkOS lands."""

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


def _request(headers: dict | None = None):
    return SimpleNamespace(headers=headers or {})


async def test_prod_ungated_lists_only_candidates(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    out = await dev_users(_request(), _FakeDB(_users()))
    assert [u["role"] for u in out] == ["candidate"]


async def test_prod_gated_lists_staff(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    out = await dev_users(_request({"x-console-gate": "1"}), _FakeDB(_users()))
    assert sorted(u["role"] for u in out) == ["admin", "candidate", "recruiter"]


async def test_dev_lists_everyone_without_gate(monkeypatch):
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    out = await dev_users(_request(), _FakeDB(_users()))
    assert sorted(u["role"] for u in out) == ["admin", "candidate", "recruiter"]


async def test_404_outside_auth_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "auth_dev_mode", False)
    with pytest.raises(AppError) as exc:
        await dev_users(_request({"x-console-gate": "1"}), _FakeDB(_users()))
    assert exc.value.code == "not_found"
