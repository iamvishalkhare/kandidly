"""API-suite fixtures: the real FastAPI app over httpx ASGITransport against a
migrated + seeded Postgres, with Redis for cache/rate-limit paths.

Opt-in via KANDIDLY_API_TESTS=1 so the default `uv run pytest` stays
datastore-free. The runner must provide, before pytest starts (settings load
once at import):

    KANDIDLY_API_TESTS=1
    KANDIDLY_DATABASE_URL=postgresql+asyncpg://... (migrated to head + seeded
        via `python -m app.db.seed` — NEVER a dev DB you care about)
    KANDIDLY_REDIS_URL=redis://...
    KANDIDLY_AUTH_DEV_MODE=true  (tests mint unsigned dev tokens)

CI wires this up in .github/workflows/ci.yml (backend-test job). Locally, use
throwaway containers on non-default ports.

Every test module here sets `pytestmark = pytest.mark.asyncio(loop_scope=
"session")`: the global asyncpg engine pools connections bound to the event
loop that created them, so all API tests must share one loop.

External services (LLM planning/scoring, LiveKit, Resend) never run: LLM jobs
are represented by their arq enqueues, which the `jobs` fixture captures
in-process; LiveKit token minting is exercised with dummy creds via the
`livekit_creds` fixture; nothing in these routes sends mail.
"""

from __future__ import annotations

import base64
import json
import os
import uuid

import httpx
import pytest
import pytest_asyncio

API_TESTS_ENABLED = os.environ.get("KANDIDLY_API_TESTS") == "1"
if not API_TESTS_ENABLED:
    collect_ignore_glob = ["test_*.py"]


# --------------------------------------------------------------------------- #
# helpers (imported by test modules)
# --------------------------------------------------------------------------- #
def mint_token(user_id, email: str, role: str) -> str:
    """Unsigned dev bearer token (app.core.security dev mode). The nonce keeps
    tokens unique so a revocation can never bleed across tests."""
    payload = {
        "user_id": str(user_id),
        "email": email,
        "role": role,
        "nonce": uuid.uuid4().hex,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def builder_payload(*, deploy: bool = True, title: str | None = None, **overrides) -> dict:
    """A valid console builder payload (ConsoleRequisitionIn). Proctoring is
    off by default; note the verification selfie is required for join preflight
    regardless (tests upload one via _upload_selfie)."""
    body = {
        "title": title or f"API Test Engineer {uuid.uuid4().hex[:8]}",
        "domain": "Engineering",
        "objective": "Screen backend fundamentals.",
        "skills": ["Python", "PostgreSQL"],
        "tone": "conversational",
        "sample_questions": [{"text": "Walk me through a system you designed."}],
        "screening_fields": [
            {"type": "text", "label": "Current company", "required": False},
            {"type": "textarea", "label": "Why this role", "required": True},
        ],
        "rubric": [
            {"name": "Python Depth", "description": "Language internals.", "weight": 40.0},
            {"name": "Data Modeling", "description": "Schema design.", "weight": 35.0},
            {"name": "Communication", "description": "Clarity.", "weight": 25.0},
        ],
        "end_date": None,
        "proctoring_enabled": False,
        "duration_minutes": 30,
        "deploy": deploy,
    }
    body.update(overrides)
    return body


VALID_ANSWERS = {"full_name": "Api Testcandidate", "why_this_role": "Strong team and stack."}


async def deploy_requisition(client, headers: dict, **overrides) -> dict:
    """Create a requisition through the console API; returns the detail body."""
    r = await client.post(
        "/api/admin/console/requisitions", json=builder_payload(**overrides), headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture(loop_scope="session", scope="session", autouse=True)
async def _preflight():
    """Fail fast with a readable message when the environment isn't wired."""
    if not API_TESTS_ENABLED:  # pragma: no cover — collect_ignore already gates
        pytest.skip("KANDIDLY_API_TESTS != 1")
    from sqlalchemy import select

    from app.core.config import settings
    from app.db.models import Organization
    from app.db.session import SessionLocal

    assert settings.auth_dev_mode, (
        "API tests need KANDIDLY_AUTH_DEV_MODE=true (set before pytest starts; "
        "settings load once at import)"
    )
    # Captcha verification would call Google siteverify when a secret is set
    # (e.g. leaked in from infra/.env on a dev box) — force the fail-open path
    # so the suite never leaves the process.
    settings.recaptcha_secret_key = ""
    async with SessionLocal() as db:
        org = (
            await db.execute(
                select(Organization).where(Organization.slug == settings.default_org_slug)
            )
        ).scalar_one_or_none()
    assert org is not None, (
        f"default org {settings.default_org_slug!r} not found — run migrations to head "
        "and `python -m app.db.seed` against KANDIDLY_DATABASE_URL first"
    )


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://apitest") as c:
        yield c


async def _staff_headers(role: str) -> dict[str, str]:
    from sqlalchemy import select

    from app.db.models import User
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        user = (
            (await db.execute(select(User).where(User.role == role).order_by(User.email)))
            .scalars()
            .first()
        )
    assert user is not None, f"no seeded {role} user — did the seed run?"
    return auth(mint_token(user.id, user.email, role))


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def admin_headers():
    return await _staff_headers("admin")


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def recruiter_headers():
    return await _staff_headers("recruiter")


@pytest_asyncio.fixture(loop_scope="session")
async def candidate():
    """A fresh candidate User row per test (claim FKs candidate_id → users)."""
    from app.core.ids import new_id
    from app.db.models import User
    from app.db.session import SessionLocal

    email = f"cand-{uuid.uuid4().hex[:10]}@apitest.dev"
    async with SessionLocal() as db:
        user = User(id=new_id(), email=email, role="candidate")
        db.add(user)
        await db.commit()
    return user


@pytest.fixture
def candidate_headers(candidate):
    return auth(mint_token(candidate.id, candidate.email, "candidate"))


@pytest.fixture
def service_headers():
    from app.core.config import settings

    return {"X-Service-Token": settings.service_token}


@pytest.fixture
def jobs(monkeypatch):
    """Capture arq enqueues in-process — the LLM planning/scoring/annotation
    chain is asserted by job name, never executed."""
    calls: list[tuple[str, tuple]] = []

    async def _record(job: str, *args, **kwargs):
        calls.append((job, args))

    import app.api.candidate as candidate_api
    import app.api.internal as internal_api
    import app.jobs.sweepers as sweepers_jobs

    monkeypatch.setattr(candidate_api, "enqueue", _record)
    monkeypatch.setattr(internal_api, "enqueue", _record)
    monkeypatch.setattr(sweepers_jobs, "enqueue", _record)
    return calls


@pytest.fixture
def stub_object_storage(monkeypatch):
    """CI has no reachable S3 (KANDIDLY_S3_ENDPOINT is deliberately dead), so
    stub the object write the selfie upload makes — preflight only checks the
    stored_files row, which the endpoint still creates."""
    from app.core import storage

    async def _noop_put(bucket: str, key: str, body: bytes, content_type: str) -> None:
        return None

    monkeypatch.setattr(storage, "put_object", _noop_put)


@pytest.fixture
def high_requisition_cap(monkeypatch):
    """Lift the free-plan requisition cap AND the cumulative interview hold
    (ER0402): the seed already fills the default org's requisition count past
    the former, and the latter is a lifetime counter that repeated full-suite
    runs against this same persistent dev DB eventually push past 50 too —
    these tests aren't about quotas."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "free_plan_max_requisitions", 10_000)
    monkeypatch.setattr(settings, "free_plan_interview_hold_at", 10_000)


@pytest.fixture
def livekit_creds(monkeypatch):
    """Dummy LiveKit creds so join can mint a room token without the real SDK
    config (minting is local HMAC — no network)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "livekit_url", "wss://apitest.livekit.invalid")
    monkeypatch.setattr(settings, "livekit_api_key", "apitest-key")
    monkeypatch.setattr(settings, "livekit_api_secret", "apitest-secret-0123456789abcdef")
