"""sweep_abandoned coverage for the 2026-07-19 incident: a candidate joins
(interview -> lobby, application -> in_interview) but the LiveKit agent never
dispatches into the room, so the interview never reaches "live". Before this
fix that left it stuck in "lobby" forever — sweep_abandoned only watched
live/paused/wrap_up, and the console ledger only shows `ended_at IS NOT
NULL` rows, so the interview was invisible with no automatic cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import Application, Interview
from app.db.session import SessionLocal
from app.jobs.sweepers import sweep_abandoned
from tests.api.test_interview_lifecycle import (
    _insert_ready_plan,
    _submitted_application,
    _upload_selfie,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _join_and_stick_in_lobby(client, admin_headers, candidate_headers) -> tuple[str, str]:
    """Drive a real application up through a successful /join, leaving the
    interview in "lobby" — exactly where a dispatch-less agent leaves it."""
    app_id, interview_id = await _submitted_application(client, admin_headers, candidate_headers)
    await client.post(
        f"/api/candidate/applications/{app_id}/consent",
        json={"consent_version": "v1-2026-07", "recording_ack": True, "monitoring_ack": True},
        headers=candidate_headers,
    )
    await _insert_ready_plan(interview_id)
    await _upload_selfie(client, app_id, candidate_headers)
    r = await client.post(f"/api/candidate/applications/{app_id}/join", headers=candidate_headers)
    assert r.status_code == 200, r.text
    return app_id, interview_id


async def _backdate_created_at(interview_id: str, seconds: int) -> None:
    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        interview.created_at = datetime.now(UTC) - timedelta(seconds=seconds)
        await db.commit()


async def test_stuck_lobby_interview_gets_swept_abandoned(
    client,
    admin_headers,
    candidate_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    app_id, interview_id = await _join_and_stick_in_lobby(client, admin_headers, candidate_headers)
    await _backdate_created_at(interview_id, 200)  # past _STALE_PRELIVE_SECONDS (120)

    await sweep_abandoned({})

    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        app = await db.get(Application, app_id)
    assert interview.status == "ended"
    assert interview.ended_at is not None
    assert interview.end_reason == "abandoned"
    assert app.state == "abandoned"
    assert ("finalize_interview", (interview_id,)) in jobs


async def test_fresh_lobby_interview_not_swept(
    client,
    admin_headers,
    candidate_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    """A candidate who just joined and is still (legitimately) waiting on the
    agent to dispatch must not be abandoned out from under them."""
    _, interview_id = await _join_and_stick_in_lobby(client, admin_headers, candidate_headers)

    await sweep_abandoned({})

    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
    assert interview.status == "lobby"
    assert interview.ended_at is None
    assert not any(job == "finalize_interview" for job, _args in jobs)


async def test_requisition_creator_sees_swept_interview_in_console(
    client,
    admin_headers,
    candidate_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    """The point of the fix: it now shows up on /console/interviews instead of
    vanishing (org-scoped ledger query, backend/app/api/console.py:939)."""
    _, interview_id = await _join_and_stick_in_lobby(client, admin_headers, candidate_headers)
    await _backdate_created_at(interview_id, 200)
    await sweep_abandoned({})

    r = await client.get("/api/admin/console/interviews", headers=admin_headers)
    assert r.status_code == 200
    assert interview_id in {row["id"] for row in r.json()}
