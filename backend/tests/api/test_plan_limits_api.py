"""Free-plan quota enforcement through the API: the console requisition cap
and the candidate-side interview hold (ER0402). The seed fills the default org
past the requisition cap, so the cap tests run against real settings."""

from __future__ import annotations

import pytest

from tests.api.conftest import builder_payload, deploy_requisition

pytestmark = pytest.mark.asyncio(loop_scope="session")

BASE = "/api/admin/console/requisitions"


async def _assert_org_at_cap(client, admin_headers) -> None:
    usage = (await client.get("/api/admin/console/usage", headers=admin_headers)).json()
    assert usage["requisitions_used"] >= usage["requisitions_limit"], (
        "precondition: the seed creates 6 requisitions ≥ the free-plan cap of "
        f"{usage['requisitions_limit']} — got {usage['requisitions_used']}"
    )


async def test_deploy_blocked_at_requisition_cap(client, admin_headers):
    await _assert_org_at_cap(client, admin_headers)
    r = await client.post(BASE, json=builder_payload(deploy=True), headers=admin_headers)
    assert r.status_code == 402
    body = r.json()
    assert body["code"] == "plan_limit"
    assert body["message"] == "Please upgrade to deploy more interviews."
    assert body["detail"]["resource"] == "requisitions"


async def test_draft_save_also_blocked_at_cap(client, admin_headers):
    await _assert_org_at_cap(client, admin_headers)
    r = await client.post(BASE, json=builder_payload(deploy=False), headers=admin_headers)
    assert r.status_code == 402
    assert "upgrade" in r.json()["message"].lower()


async def test_claim_hold_er0402(
    client, admin_headers, candidate_headers, high_requisition_cap, monkeypatch
):
    from app.core.config import settings

    req = await deploy_requisition(client, admin_headers, deploy=True)

    monkeypatch.setattr(settings, "free_plan_interview_hold_at", 0)
    r = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert r.status_code == 402
    body = r.json()
    assert body["code"] == "plan_limit"
    assert body["detail"]["error_code"] == "ER0402"
    assert body["message"] == (
        "This interview is on hold. Please contact your recruiter for more details."
    )


async def test_submit_rechecks_hold(
    client, admin_headers, candidate_headers, high_requisition_cap, jobs, monkeypatch
):
    """A claim that slipped under the threshold must not create an Interview
    once the org is past it (the submit-time re-check)."""
    from app.core.config import settings
    from tests.api.conftest import VALID_ANSWERS

    req = await deploy_requisition(client, admin_headers, deploy=True)
    claim = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    app_id = claim.json()["application_id"]
    await client.patch(
        f"/api/candidate/applications/{app_id}/form",
        json={"answers_partial": VALID_ANSWERS},
        headers=candidate_headers,
    )

    monkeypatch.setattr(settings, "free_plan_interview_hold_at", 0)
    r = await client.post(
        f"/api/candidate/applications/{app_id}/form/submit", headers=candidate_headers
    )
    assert r.status_code == 402
    assert r.json()["detail"]["error_code"] == "ER0402"
    assert jobs == []  # no interview → no planning jobs


async def test_usage_endpoint_reports_quota(client, admin_headers):
    from app.core.config import settings

    r = await client.get("/api/admin/console/usage", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "free"
    assert body["requisitions_limit"] == settings.free_plan_max_requisitions
    assert body["interviews_hold_at"] == settings.free_plan_interview_hold_at
    assert body["requisitions_used"] >= 1
    assert body["interviews_used"] >= 1
