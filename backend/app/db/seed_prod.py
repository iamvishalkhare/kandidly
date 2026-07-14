"""Minimal production seed (docs/deploy-ec2.md). Idempotent: safe to re-run.

Creates only what a fresh prod box needs: the catalog autocomplete entries and
a bootstrap admin account — no demo requisitions, interviews, or media (that is
app.db.seed, dev-only). Optionally also creates one shared test-candidate
account: until real candidate auth lands, the /i/<token> landing page can only
authenticate candidates that already exist as users.

Unlike the dev seed, account ids are random (new_id), not derived from the
email: under AUTH_DEV_MODE a printed dev token is only as hard to forge as the
UUID inside it, so it must not be reproducible from public code.

Requires migrations at head (the default org row is created by 0003).

Run (one-off container on the server):
    docker compose -f infra/compose.prod.yml run --rm backend \
        uv run python -m app.db.seed_prod

Reads KANDIDLY_BOOTSTRAP_ADMIN_EMAIL (required) and
KANDIDLY_BOOTSTRAP_CANDIDATE_EMAIL (optional) from the environment.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.core.ids import new_id
from app.db.models import User
from app.db.seed import _dev_token, _ensure_catalog, _ensure_org
from app.db.session import SessionLocal


async def _get_or_create_user(db, email: str, role: str, org_id=None) -> tuple[User, bool]:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing, False
    user = User(
        id=new_id(),
        email=email,
        role=role,
        org_id=org_id if role != "candidate" else None,
    )
    db.add(user)
    await db.flush()
    return user, True


async def seed() -> None:
    admin_email = os.environ.get("KANDIDLY_BOOTSTRAP_ADMIN_EMAIL", "").strip()
    candidate_email = os.environ.get("KANDIDLY_BOOTSTRAP_CANDIDATE_EMAIL", "").strip()
    if not admin_email:
        raise SystemExit("KANDIDLY_BOOTSTRAP_ADMIN_EMAIL is required (set it in infra/.env.prod)")

    async with SessionLocal() as db:
        org = await _ensure_org(db)

        admin, admin_created = await _get_or_create_user(db, admin_email, "admin", org_id=org.id)
        candidate = None
        if candidate_email:
            candidate, _ = await _get_or_create_user(db, candidate_email, "candidate")

        await _ensure_catalog(db, org.id, admin.id)
        await db.commit()

        print("\n=== Kandidly prod seed ===")
        print(f"org: {org.slug}")
        print(f"admin: {admin.email} ({'created' if admin_created else 'already present'})")
        if admin_created:
            # Emergency/API access; the normal path is the console login screen
            # behind the Caddy gate. Not reprinted on later runs.
            print(f"admin dev-token (store securely, shown once): {_dev_token(admin)}")
        if candidate is not None:
            print(f"test candidate: {candidate.email}")
        print("catalog entries ensured.\n")


if __name__ == "__main__":
    asyncio.run(seed())
