"""DELETE /api/admin/console/interviews/{id} — hardcoded to one operator
email so the feature can be exercised in prod without shipping it to every
console user, and expected to wipe DB rows, S3 objects, and the Redis
context cache so the candidate can attempt the same invite again."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.ids import new_id
from app.db.models import (
    Application,
    AuditLog,
    Evaluation,
    EvidenceNote,
    Injection,
    Interview,
    ProctoringEvent,
    ProctoringSnapshot,
    QuestionPlan,
    Report,
    ScoringJob,
    StoredFile,
    Turn,
)
from app.db.session import SessionLocal
from app.domain.interview_context import get_cached_context
from tests.api.conftest import VALID_ANSWERS, auth, mint_token
from tests.api.test_interview_lifecycle import _insert_ready_plan, _upload_selfie

pytestmark = pytest.mark.asyncio(loop_scope="session")

ALLOWED_EMAIL = "vishalkhare39@gmail.com"


def _allowed_headers() -> dict[str, str]:
    """Dev token for the one email the delete endpoint accepts. No matching
    User row is needed — _org_id_for/_ensure_can_delete_interviews both fall
    back gracefully (default org; email straight off the token)."""
    return auth(mint_token(new_id(), ALLOWED_EMAIL, "admin"))


async def _insert_report(interview_id: str) -> None:
    async with SessionLocal() as db:
        db.add(
            Report(
                id=new_id(),
                interview_id=interview_id,
                overall_score=72.5,
                summary="Solid fundamentals, some gaps in system design.",
                strengths=["Clear communicator"],
                concerns=["Limited depth on scaling"],
                coverage=["python", "postgres"],
                proctoring_summary={},
            )
        )
        await db.commit()


async def _full_interview_with_artifacts(
    client, admin_headers, candidate_headers, service_headers
) -> tuple[str, str]:
    """Deploy (proctoring on) -> submit -> consent -> plan -> selfie -> join
    -> live -> one turn + one snapshot -> ended -> a Report row. Exercises
    every table the delete endpoint must clean up."""
    from tests.api.conftest import deploy_requisition

    req = await deploy_requisition(client, admin_headers, deploy=True, proctoring_enabled=True)
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
    interview_id = submit.json()["interview_id"]

    await client.post(
        f"/api/candidate/applications/{app_id}/consent",
        json={"consent_version": "v1-2026-07", "recording_ack": True, "monitoring_ack": True},
        headers=candidate_headers,
    )
    await _insert_ready_plan(interview_id)
    await _upload_selfie(client, app_id, candidate_headers)
    r = await client.post(f"/api/candidate/applications/{app_id}/join", headers=candidate_headers)
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/internal/interviews/{interview_id}/status",
        json={"status": "live"},
        headers=service_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/internal/interviews/{interview_id}/turns",
        json={
            "seq": 1,
            "speaker": "kandidly",
            "text": "Tell me about a system you designed.",
            "started_at": datetime.now(UTC).isoformat(),
        },
        headers=service_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/api/candidate/interviews/{interview_id}/snapshots",
        files={"image": ("frame.webp", b"not-a-real-webp", "image/webp")},
        data={"captured_at": datetime.now(UTC).isoformat()},
        headers=candidate_headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/internal/interviews/{interview_id}/status",
        json={"status": "ended", "end_reason": "completed", "elapsed_active_seconds": 900},
        headers=service_headers,
    )
    assert r.status_code == 200, r.text

    await _insert_report(interview_id)
    return app_id, interview_id


async def test_delete_forbidden_for_non_designated_admin(
    client,
    admin_headers,
    candidate_headers,
    service_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    _, interview_id = await _full_interview_with_artifacts(
        client, admin_headers, candidate_headers, service_headers
    )
    r = await client.delete(f"/api/admin/console/interviews/{interview_id}", headers=admin_headers)
    assert r.status_code == 403

    # Untouched — the 403 must be a no-op, not a partial delete.
    async with SessionLocal() as db:
        assert await db.get(Interview, interview_id) is not None


async def test_delete_wipes_db_s3_and_redis(
    client,
    admin_headers,
    candidate_headers,
    service_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    app_id, interview_id = await _full_interview_with_artifacts(
        client, admin_headers, candidate_headers, service_headers
    )

    # Sanity: the artifacts we're about to assert got deleted actually exist.
    assert await get_cached_context(interview_id) is not None
    async with SessionLocal() as db:
        assert (await db.execute(select(Turn).where(Turn.interview_id == interview_id))).first()
        assert (
            await db.execute(
                select(ProctoringSnapshot).where(ProctoringSnapshot.interview_id == interview_id)
            )
        ).first()
        assert (await db.execute(select(Report).where(Report.interview_id == interview_id))).first()
    snapshot_keys_before = [
        k for (_b, k) in stub_object_storage if k.startswith(f"{interview_id}/")
    ]
    assert snapshot_keys_before, "expected the uploaded snapshot to land in the fake bucket"

    r = await client.delete(
        f"/api/admin/console/interviews/{interview_id}", headers=_allowed_headers()
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    async with SessionLocal() as db:
        assert await db.get(Interview, interview_id) is None
        for model in (
            Turn,
            ProctoringSnapshot,
            ProctoringEvent,
            EvidenceNote,
            Injection,
            Evaluation,
            ScoringJob,
            Report,
            QuestionPlan,
        ):
            rows = (
                await db.execute(select(model).where(model.interview_id == interview_id))
            ).first()
            assert rows is None, f"{model.__name__} row survived the delete"

        app = await db.get(Application, app_id)
        assert app.interview_id is None
        assert app.state == "abandoned"

        audit = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "interview",
                    AuditLog.entity_id == uuid.UUID(interview_id),
                    AuditLog.action == "interview.deleted",
                )
            )
        ).scalar_one_or_none()
        assert audit is not None

    # StoredFile rows for the deleted snapshot are gone too, not just the
    # proctoring_snapshots row that pointed at them.
    async with SessionLocal() as db:
        remaining_selfie_or_snapshot = (
            (await db.execute(select(StoredFile).where(StoredFile.bucket == "kandidly-snapshots")))
            .scalars()
            .all()
        )
    assert all(str(interview_id) not in f.key for f in remaining_selfie_or_snapshot)

    assert not [k for (b, k) in stub_object_storage if k.startswith(f"{interview_id}/")]
    assert await get_cached_context(interview_id) is None


async def test_re_claim_after_delete_starts_fresh_interview(
    client,
    admin_headers,
    candidate_headers,
    service_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
):
    """The whole point: the candidate can attempt the same invite again."""
    from tests.api.conftest import deploy_requisition

    req = await deploy_requisition(client, admin_headers, deploy=True, proctoring_enabled=True)
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
    interview_id = submit.json()["interview_id"]

    r = await client.delete(
        f"/api/admin/console/interviews/{interview_id}", headers=_allowed_headers()
    )
    assert r.status_code == 200, r.text

    claim2 = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert claim2.status_code == 200, claim2.text
    assert claim2.json()["application_id"] != app_id
