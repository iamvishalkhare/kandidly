"""Console requisition CRUD + publish through the real API surface."""

from __future__ import annotations

import pytest

from tests.api.conftest import auth, builder_payload, deploy_requisition, mint_token

pytestmark = pytest.mark.asyncio(loop_scope="session")

BASE = "/api/admin/console/requisitions"


async def test_console_requires_auth(client):
    r = await client.get(BASE)
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


async def test_console_rejects_candidate_role(client, candidate):
    headers = auth(mint_token(candidate.id, candidate.email, "candidate"))
    r = await client.get(BASE, headers=headers)
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


async def test_deploy_publishes_requisition(client, admin_headers, high_requisition_cap):
    body = await deploy_requisition(client, admin_headers, deploy=True)
    assert body["status"] == "open"
    assert body["live"] is True
    assert body["code"].startswith("REQ-")
    assert body["opens_at"] is not None
    assert body["invite_token"]  # open invite link created in the same transaction

    detail = await client.get(f"{BASE}/{body['id']}", headers=admin_headers)
    assert detail.status_code == 200
    got = detail.json()
    assert got["title"] == body["title"]
    # full_name is injected server-side and hidden from the builder round-trip
    labels = [f["label"] for f in got["screening_fields"]]
    assert "Why this role" in labels and "Full name" not in labels
    assert [c["name"] for c in got["rubric"]] == ["Python Depth", "Data Modeling", "Communication"]


async def test_save_offline_is_paused_not_live(client, admin_headers, high_requisition_cap):
    body = await deploy_requisition(client, admin_headers, deploy=False)
    assert body["status"] == "paused"
    assert body["live"] is False
    assert body["opens_at"] is None


async def test_deploy_with_no_skills_rejected(client, admin_headers, high_requisition_cap):
    r = await client.post(BASE, json=builder_payload(deploy=True, skills=[]), headers=admin_headers)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


async def test_update_requisition(client, recruiter_headers, high_requisition_cap):
    created = await deploy_requisition(client, recruiter_headers, deploy=False)

    update = builder_payload(deploy=True, title="Updated Api Test Engineer")
    update["screening_fields"].append(
        {"type": "multiple_choice", "label": "Notice period", "options": ["<30d", "30-60d"]}
    )
    r = await client.put(f"{BASE}/{created['id']}", json=update, headers=recruiter_headers)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["title"] == "Updated Api Test Engineer"
    assert got["status"] == "open"  # deploy=True flips paused → open
    assert "Notice period" in [f["label"] for f in got["screening_fields"]]


async def test_soft_delete_removes_from_console(client, admin_headers, high_requisition_cap):
    created = await deploy_requisition(client, admin_headers, deploy=True)

    r = await client.delete(f"{BASE}/{created['id']}", headers=admin_headers)
    assert r.status_code == 200 and r.json() == {"ok": True}

    assert (await client.get(f"{BASE}/{created['id']}", headers=admin_headers)).status_code == 404
    listing = await client.get(BASE, headers=admin_headers)
    assert created["id"] not in [row["id"] for row in listing.json()]

    # its invite link stops resolving for candidates
    resolved = await client.get(f"/api/public/i/{created['invite_token']}")
    assert resolved.status_code == 200
    assert resolved.json()["status_ok"] is False
