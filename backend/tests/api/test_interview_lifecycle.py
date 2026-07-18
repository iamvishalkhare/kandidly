"""Interview lifecycle over the API: consent → join preflight → internal
status transitions, with the LLM plan/scoring jobs mocked at the enqueue
boundary (a plan row is inserted directly, standing in for generate_plan)."""

from __future__ import annotations

import pytest

from tests.api.conftest import VALID_ANSWERS, deploy_requisition

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _submitted_application(client, admin_headers, candidate_headers) -> tuple[str, str]:
    """Deploy → claim → autosave → submit; returns (application_id, interview_id)."""
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
    submit = await client.post(
        f"/api/candidate/applications/{app_id}/form/submit", headers=candidate_headers
    )
    assert submit.status_code == 200, submit.text
    return app_id, submit.json()["interview_id"]


async def _insert_ready_plan(interview_id: str) -> None:
    """What the (mocked) generate_plan job would leave behind."""
    from app.core.ids import new_id
    from app.db.models import QuestionPlan
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        db.add(
            QuestionPlan(
                id=new_id(),
                interview_id=interview_id,
                status="ready",
                generated_by_model="mock",
                prompt_version="apitest-v0",
                total_budget_seconds=1500,
            )
        )
        await db.commit()


async def _state(client, app_id: str, headers) -> str:
    r = await client.get(f"/api/candidate/applications/{app_id}", headers=headers)
    return r.json()["state"]


async def _upload_selfie(client, app_id: str, headers) -> None:
    """The verification selfie is required before every first join, regardless
    of the requisition's proctoring toggle."""
    r = await client.post(
        f"/api/candidate/applications/{app_id}/selfie",
        files={"image": ("selfie.webp", b"not-a-real-webp", "image/webp")},
        headers=headers,
    )
    assert r.status_code == 200, r.text


async def test_full_lifecycle_to_completed(
    client,
    admin_headers,
    candidate_headers,
    service_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    app_id, interview_id = await _submitted_application(client, admin_headers, candidate_headers)

    # consent → in_lobby
    r = await client.post(
        f"/api/candidate/applications/{app_id}/consent",
        json={"consent_version": "v1-2026-07", "recording_ack": True, "monitoring_ack": True},
        headers=candidate_headers,
    )
    assert r.status_code == 200
    assert await _state(client, app_id, candidate_headers) == "in_lobby"

    # join before the plan exists → 202 not_ready (the plan job is mocked)
    r = await client.post(f"/api/candidate/applications/{app_id}/join", headers=candidate_headers)
    assert r.status_code == 202
    assert r.json()["code"] == "not_ready"

    await _insert_ready_plan(interview_id)

    # plan ready but no verification selfie yet → still 202 (selfie is
    # required even with proctoring off)
    r = await client.post(f"/api/candidate/applications/{app_id}/join", headers=candidate_headers)
    assert r.status_code == 202
    await _upload_selfie(client, app_id, candidate_headers)
    # retake: same fixed key must update, not violate the (bucket, key) unique
    await _upload_selfie(client, app_id, candidate_headers)

    # join → token minted, app → in_interview, interview created → lobby
    r = await client.post(f"/api/candidate/applications/{app_id}/join", headers=candidate_headers)
    assert r.status_code == 200, r.text
    join = r.json()
    assert join["token"]
    assert join["room_name"] == f"kndl-{interview_id}"
    assert join["proctoring"]["enabled"] is False
    assert await _state(client, app_id, candidate_headers) == "in_interview"

    boot = await client.get(
        f"/internal/interviews/{interview_id}/bootstrap", headers=service_headers
    )
    assert boot.status_code == 200
    assert boot.json()["interview"]["status"] == "lobby"

    # agent drives the interview: lobby → live → wrap_up → ended
    for status in ("live", "wrap_up"):
        r = await client.post(
            f"/internal/interviews/{interview_id}/status",
            json={"status": status},
            headers=service_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status

    r = await client.post(
        f"/internal/interviews/{interview_id}/status",
        json={"status": "ended", "end_reason": "completed", "elapsed_active_seconds": 900},
        headers=service_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ended"

    # interview terminal mirrors to the application + kicks off finalize
    assert await _state(client, app_id, candidate_headers) == "completed"
    assert ("finalize_interview", (interview_id,)) in jobs

    # terminal: no going back
    r = await client.post(
        f"/internal/interviews/{interview_id}/status",
        json={"status": "live"},
        headers=service_headers,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_transition"


async def test_illegal_status_jump_rejected(
    client, admin_headers, candidate_headers, service_headers, high_requisition_cap, jobs
):
    _, interview_id = await _submitted_application(client, admin_headers, candidate_headers)

    # created → live skips lobby
    r = await client.post(
        f"/internal/interviews/{interview_id}/status",
        json={"status": "live"},
        headers=service_headers,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_transition"


async def test_abandoned_end_reason_mirrors_application(
    client,
    admin_headers,
    candidate_headers,
    service_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    app_id, interview_id = await _submitted_application(client, admin_headers, candidate_headers)
    await client.post(
        f"/api/candidate/applications/{app_id}/consent",
        json={"consent_version": "v1-2026-07", "recording_ack": True, "monitoring_ack": True},
        headers=candidate_headers,
    )
    await _insert_ready_plan(interview_id)
    await _upload_selfie(client, app_id, candidate_headers)
    assert (
        await client.post(f"/api/candidate/applications/{app_id}/join", headers=candidate_headers)
    ).status_code == 200

    for body in (
        {"status": "live"},
        {"status": "ended", "end_reason": "abandoned"},
    ):
        r = await client.post(
            f"/internal/interviews/{interview_id}/status", json=body, headers=service_headers
        )
        assert r.status_code == 200, r.text

    assert await _state(client, app_id, candidate_headers) == "abandoned"
    assert ("finalize_interview", (interview_id,)) in jobs


async def test_internal_api_requires_service_token(client):
    r = await client.get("/internal/interviews/00000000-0000-0000-0000-000000000000/bootstrap")
    assert r.status_code == 401
