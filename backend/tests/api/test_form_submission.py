"""Screening form autosave + submit (Interview row creation, job enqueues)."""

from __future__ import annotations

import pytest

from tests.api.conftest import VALID_ANSWERS, deploy_requisition

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _claimed_application(client, admin_headers, candidate_headers) -> str:
    req = await deploy_requisition(client, admin_headers, deploy=True)
    r = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["application_id"]


async def test_autosave_merges_and_advances_state(
    client, admin_headers, candidate_headers, high_requisition_cap
):
    app_id = await _claimed_application(client, admin_headers, candidate_headers)

    r = await client.patch(
        f"/api/candidate/applications/{app_id}/form",
        json={"answers_partial": {"full_name": "Api Testcandidate"}},
        headers=candidate_headers,
    )
    assert r.status_code == 200

    r = await client.patch(
        f"/api/candidate/applications/{app_id}/form",
        json={"answers_partial": {"why_this_role": "Strong team and stack."}},
        headers=candidate_headers,
    )
    assert r.status_code == 200

    got = await client.get(f"/api/candidate/applications/{app_id}", headers=candidate_headers)
    body = got.json()
    assert body["state"] == "form_in_progress"
    assert body["answers"] == VALID_ANSWERS  # shallow merge kept both patches


async def test_submit_requires_required_fields(
    client, admin_headers, candidate_headers, high_requisition_cap, jobs
):
    app_id = await _claimed_application(client, admin_headers, candidate_headers)
    await client.patch(
        f"/api/candidate/applications/{app_id}/form",
        json={"answers_partial": {"full_name": "Api Testcandidate"}},  # missing required textarea
        headers=candidate_headers,
    )
    r = await client.post(
        f"/api/candidate/applications/{app_id}/form/submit", headers=candidate_headers
    )
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
    assert jobs == []  # nothing enqueued on a failed submit


async def test_submit_creates_interview_and_enqueues_planning(
    client, admin_headers, candidate_headers, high_requisition_cap, jobs
):
    app_id = await _claimed_application(client, admin_headers, candidate_headers)
    await client.patch(
        f"/api/candidate/applications/{app_id}/form",
        json={"answers_partial": VALID_ANSWERS},
        headers=candidate_headers,
    )
    r = await client.post(
        f"/api/candidate/applications/{app_id}/form/submit", headers=candidate_headers
    )
    assert r.status_code == 200, r.text
    interview_id = r.json()["interview_id"]

    # The LLM planning chain is mocked at the enqueue boundary.
    assert [name for name, _ in jobs] == ["generate_plan", "enrich_sources"]
    assert jobs[0][1] == (interview_id,)

    got = (
        await client.get(f"/api/candidate/applications/{app_id}", headers=candidate_headers)
    ).json()
    assert got["state"] == "form_submitted"
    assert got["interview_id"] == interview_id

    # the form is frozen after submit
    r = await client.patch(
        f"/api/candidate/applications/{app_id}/form",
        json={"answers_partial": {"full_name": "Changed"}},
        headers=candidate_headers,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


async def test_application_is_owner_scoped(
    client, admin_headers, candidate_headers, high_requisition_cap, candidate
):
    from app.core.ids import new_id
    from app.db.models import User
    from app.db.session import SessionLocal
    from tests.api.conftest import auth, mint_token

    app_id = await _claimed_application(client, admin_headers, candidate_headers)

    async with SessionLocal() as db:
        other = User(id=new_id(), email=f"nosy-{new_id().hex[:10]}@apitest.dev", role="candidate")
        db.add(other)
        await db.commit()
    r = await client.get(
        f"/api/candidate/applications/{app_id}",
        headers=auth(mint_token(other.id, other.email, "candidate")),
    )
    assert r.status_code in (403, 404)
