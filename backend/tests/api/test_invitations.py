"""Org-wide invitations ledger (GET /api/admin/console/invitations): pagination,
derived status, and every filter. The suite runs against a persistent dev DB, so
assertions scope themselves with a per-test unique email fragment (via `q`) or
requisition code — never absolute totals."""

from __future__ import annotations

import uuid

import pytest

from app.core.ids import new_id
from app.db.models import Organization, User
from app.db.session import SessionLocal
from tests.api.conftest import auth, deploy_requisition, mint_token
from tests.api.test_invite_only import _add, _new_candidate

pytestmark = pytest.mark.asyncio(loop_scope="session")

URL = "/api/admin/console/invitations"


async def _list(client, headers, **params) -> dict:
    r = await client.get(URL, params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_lists_across_requisitions_paginated_newest_first(
    client, admin_headers, high_requisition_cap, jobs
):
    tag = uuid.uuid4().hex[:8]
    req_a = await deploy_requisition(client, admin_headers, invite_only=True)
    req_b = await deploy_requisition(client, admin_headers, invite_only=True)
    for req, count in ((req_a, 3), (req_b, 2)):
        await _add(
            client,
            admin_headers,
            req["id"],
            [
                {"email": f"{tag}-{req['code']}-{i}@apitest.dev".lower(), "first_name": "Pat"}
                for i in range(count)
            ],
        )

    page = await _list(client, admin_headers, q=tag)
    assert page["total"] == 5
    assert len(page["items"]) == 5
    assert {i["requisition_code"] for i in page["items"]} == {req_a["code"], req_b["code"]}
    assert all(i["status"] == "invited" and i["revoked_at"] is None for i in page["items"])
    # requisition_id is what the UI links to (/console/requisitions/:id).
    assert {i["requisition_id"] for i in page["items"]} == {req_a["id"], req_b["id"]}

    # Pagination: stable order, no overlap between pages, totals unchanged.
    first = await _list(client, admin_headers, q=tag, limit=2)
    assert (first["total"], first["offset"], first["limit"]) == (5, 0, 2)
    assert len(first["items"]) == 2
    rest = await _list(client, admin_headers, q=tag, limit=3, offset=2)
    assert len(rest["items"]) == 3
    ids = [i["id"] for i in first["items"]] + [i["id"] for i in rest["items"]]
    assert len(set(ids)) == 5
    assert ids == [i["id"] for i in page["items"]]


async def test_search_matches_name_and_email(client, admin_headers, high_requisition_cap, jobs):
    tag = uuid.uuid4().hex[:8]
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    await _add(
        client,
        admin_headers,
        req["id"],
        [
            {"email": f"{tag}-a@apitest.dev", "first_name": "Zora", "last_name": f"Only{tag}"},
            {"email": f"{tag}-b@apitest.dev", "first_name": "Mira", "last_name": "Other"},
        ],
    )
    by_name = await _list(client, admin_headers, q=f"zora only{tag}")
    assert [i["email"] for i in by_name["items"]] == [f"{tag}-a@apitest.dev"]
    by_email = await _list(client, admin_headers, q=f"{tag}-b@")
    assert [i["email"] for i in by_email["items"]] == [f"{tag}-b@apitest.dev"]


async def test_requisition_code_and_date_filters(client, admin_headers, high_requisition_cap, jobs):
    tag = uuid.uuid4().hex[:8]
    req_a = await deploy_requisition(client, admin_headers, invite_only=True)
    req_b = await deploy_requisition(client, admin_headers, invite_only=True)
    for req in (req_a, req_b):
        await _add(
            client, admin_headers, req["id"], [{"email": f"{tag}-{req['id'][:6]}@apitest.dev"}]
        )

    scoped = await _list(client, admin_headers, q=tag, requisition_code=req_a["code"])
    assert scoped["total"] == 1
    assert scoped["items"][0]["requisition_code"] == req_a["code"]

    assert (await _list(client, admin_headers, q=tag, created_after="2099-01-01T00:00:00Z"))[
        "total"
    ] == 0
    assert (await _list(client, admin_headers, q=tag, created_before="2099-01-01T00:00:00Z"))[
        "total"
    ] == 2
    # Naive bounds are accepted (taken as UTC) — the UI sends ISO with Z anyway.
    assert (await _list(client, admin_headers, q=tag, created_after="2099-01-01T00:00:00"))[
        "total"
    ] == 0


async def test_status_filter_tracks_application_progress(
    client, admin_headers, high_requisition_cap, jobs
):
    tag = uuid.uuid4().hex[:8]
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    cand, cand_headers = await _new_candidate(f"{tag}-claimer@apitest.dev")
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": cand.email, "first_name": "C"}, {"email": f"{tag}-idle@apitest.dev"}],
    )
    r = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=cand_headers)
    assert r.status_code == 200, r.text

    everyone = await _list(client, admin_headers, q=tag)
    assert {i["email"]: i["status"] for i in everyone["items"]} == {
        cand.email: "claimed",
        f"{tag}-idle@apitest.dev": "invited",
    }
    claimed = await _list(client, admin_headers, q=tag, status="claimed")
    assert [i["email"] for i in claimed["items"]] == [cand.email]
    assert claimed["total"] == 1
    invited = await _list(client, admin_headers, q=tag, status="invited")
    assert [i["email"] for i in invited["items"]] == [f"{tag}-idle@apitest.dev"]
    assert (await _list(client, admin_headers, q=tag, status="completed"))["total"] == 0


async def test_access_filter_defaults_to_active(client, admin_headers, high_requisition_cap, jobs):
    tag = uuid.uuid4().hex[:8]
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": f"{tag}-gone@apitest.dev"}, {"email": f"{tag}-here@apitest.dev"}],
    )
    doomed = (await _list(client, admin_headers, q=f"{tag}-gone"))["items"][0]
    r = await client.delete(
        f"/api/admin/console/requisitions/{req['id']}/invites/{doomed['id']}",
        headers=admin_headers,
    )
    assert r.status_code == 200

    active = await _list(client, admin_headers, q=tag)
    assert [i["email"] for i in active["items"]] == [f"{tag}-here@apitest.dev"]
    revoked = await _list(client, admin_headers, q=tag, access="revoked")
    assert [i["email"] for i in revoked["items"]] == [f"{tag}-gone@apitest.dev"]
    assert revoked["items"][0]["revoked_at"] is not None


async def test_other_org_sees_nothing(client, admin_headers, high_requisition_cap, jobs):
    tag = uuid.uuid4().hex[:8]
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    await _add(client, admin_headers, req["id"], [{"email": f"{tag}-mine@apitest.dev"}])

    async with SessionLocal() as db:
        other_org = Organization(id=new_id(), name="Elsewhere", slug=f"elsewhere-{tag}")
        outsider = User(
            id=new_id(), email=f"{tag}-admin@elsewhere.dev", role="admin", org_id=other_org.id
        )
        db.add_all([other_org, outsider])
        await db.commit()
    outsider_headers = auth(mint_token(outsider.id, outsider.email, "admin"))
    assert (await _list(client, outsider_headers, q=tag))["total"] == 0


async def test_requires_staff_role(client, jobs):
    _, cand_headers = await _new_candidate()
    r = await client.get(URL, headers=cand_headers)
    assert r.status_code == 403
