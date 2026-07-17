"""Invite link resolution (public) + claim (candidate)."""

from __future__ import annotations

import pytest

from tests.api.conftest import auth, deploy_requisition, mint_token

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_resolve_unknown_token_never_404s(client):
    r = await client.get("/api/public/i/not-a-real-token")
    assert r.status_code == 200
    body = r.json()
    assert body["status_ok"] is False
    assert body["title"] is None


async def test_resolve_open_link(client, admin_headers, high_requisition_cap):
    req = await deploy_requisition(client, admin_headers, deploy=True)
    r = await client.get(f"/api/public/i/{req['invite_token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["status_ok"] is True
    assert body["title"] == req["title"]

    # landing-page views count as clicks on the console card
    detail = await client.get(f"/api/admin/console/requisitions/{req['id']}", headers=admin_headers)
    assert detail.json()["clicks"] >= 1


async def test_resolve_offline_link_not_usable(client, admin_headers, high_requisition_cap):
    req = await deploy_requisition(client, admin_headers, deploy=False)  # paused
    r = await client.get(f"/api/public/i/{req['invite_token']}")
    assert r.status_code == 200
    assert r.json()["status_ok"] is False


async def test_claim_requires_candidate_role(client, admin_headers, high_requisition_cap):
    req = await deploy_requisition(client, admin_headers, deploy=True)
    r = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=admin_headers)
    assert r.status_code == 403


async def test_claim_creates_application_idempotently(
    client, admin_headers, candidate_headers, high_requisition_cap
):
    req = await deploy_requisition(client, admin_headers, deploy=True)

    first = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["state"] == "registered"

    again = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert again.status_code == 200
    assert again.json()["application_id"] == body["application_id"]


async def test_claim_invalid_token_rejected(client, candidate_headers):
    r = await client.post("/api/candidate/i/not-a-real-token/claim", headers=candidate_headers)
    assert r.status_code == 400
    assert r.json()["code"] == "link_invalid"


async def test_second_candidate_gets_own_application(
    client, admin_headers, candidate_headers, high_requisition_cap, candidate
):
    from app.core.ids import new_id
    from app.db.models import User
    from app.db.session import SessionLocal

    req = await deploy_requisition(client, admin_headers, deploy=True)
    mine = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert mine.status_code == 200

    async with SessionLocal() as db:
        other = User(id=new_id(), email=f"other-{new_id().hex[:10]}@apitest.dev", role="candidate")
        db.add(other)
        await db.commit()
    theirs = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim",
        headers=auth(mint_token(other.id, other.email, "candidate")),
    )
    assert theirs.status_code == 200
    assert theirs.json()["application_id"] != mine.json()["application_id"]
