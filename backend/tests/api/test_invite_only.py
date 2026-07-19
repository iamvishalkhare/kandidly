"""Invite-only requisitions: the builder toggle, the guest-list console API
(add / import / revoke / resend + derived status), claim enforcement for
uninvited vs invited candidates, and the candidate_invite fan-out (enqueues
captured via the jobs fixture; delivery itself exercised through the real
send_invite_email job over the console transport)."""

from __future__ import annotations

import io
import uuid

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.core.ids import new_id
from app.db.models import RequisitionInvite, User
from app.db.session import SessionLocal
from tests.api.conftest import VALID_ANSWERS, auth, deploy_requisition, mint_token

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _new_candidate(email: str | None = None) -> tuple[User, dict[str, str]]:
    email = email or f"cand-{uuid.uuid4().hex[:10]}@apitest.dev"
    async with SessionLocal() as db:
        user = User(id=new_id(), email=email, role="candidate")
        db.add(user)
        await db.commit()
    return user, auth(mint_token(user.id, user.email, "candidate"))


def _invites_url(req_id: str) -> str:
    return f"/api/admin/console/requisitions/{req_id}/invites"


async def _add(client, headers, req_id: str, invites: list[dict]):
    return await client.post(_invites_url(req_id), json={"invites": invites}, headers=headers)


# --------------------------------------------------------------------------- #
# claim enforcement
# --------------------------------------------------------------------------- #
async def test_uninvited_candidate_cannot_claim(client, admin_headers, high_requisition_cap, jobs):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    assert req["invite_only"] is True
    _, cand_headers = await _new_candidate()
    r = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=cand_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["reason"] == "not_invited"


async def test_invited_email_claims_case_insensitively(
    client, admin_headers, high_requisition_cap, jobs
):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    cand, cand_headers = await _new_candidate(f"Mixed.Case-{uuid.uuid4().hex[:6]}@Apitest.DEV")
    r = await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": cand.email, "first_name": "Mixed", "last_name": "Case"}],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"added": 1, "duplicates": 0, "invalid": []}

    r = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=cand_headers)
    assert r.status_code == 200, r.text


async def test_open_requisition_ignores_guest_list(
    client, admin_headers, high_requisition_cap, jobs
):
    req = await deploy_requisition(client, admin_headers, invite_only=False)
    _, cand_headers = await _new_candidate()
    r = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=cand_headers)
    assert r.status_code == 200, r.text


async def test_landing_exposes_invite_only(client, admin_headers, high_requisition_cap, jobs):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    r = await client.get(f"/api/public/i/{req['invite_token']}")
    assert r.status_code == 200
    assert r.json()["invite_only"] is True


async def test_revoke_blocks_future_claims_but_not_mid_flight(
    client, admin_headers, high_requisition_cap, jobs
):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    cand, cand_headers = await _new_candidate()
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": cand.email, "first_name": "A", "last_name": "B"}],
    )
    claim = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=cand_headers)
    assert claim.status_code == 200

    invites = (await client.get(_invites_url(req["id"]), headers=admin_headers)).json()
    assert invites[0]["status"] == "claimed"
    r = await client.delete(f"{_invites_url(req['id'])}/{invites[0]['id']}", headers=admin_headers)
    assert r.status_code == 200

    # Mid-flight candidate re-enters their existing application…
    again = await client.post(f"/api/candidate/i/{req['invite_token']}/claim", headers=cand_headers)
    assert again.status_code == 200
    assert again.json()["application_id"] == claim.json()["application_id"]
    # …and the revoked row is gone from the console list.
    assert (await client.get(_invites_url(req["id"]), headers=admin_headers)).json() == []


# --------------------------------------------------------------------------- #
# console guest-list API
# --------------------------------------------------------------------------- #
async def test_add_reports_invalid_and_duplicates_and_enqueues_emails(
    client, admin_headers, high_requisition_cap, jobs
):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    r = await _add(
        client,
        admin_headers,
        req["id"],
        [
            {"email": "JORDAN@apitest.dev", "first_name": "Jordan", "last_name": "Lee"},
            {"email": "jordan@apitest.dev", "first_name": "Dupe", "last_name": "Row"},
            {"email": "not-an-email", "first_name": "Bad", "last_name": "Row"},
        ],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "added": 1,
        "duplicates": 1,
        "invalid": [{"row": 3, "reason": "invalid email"}],
    }
    sends = [args for (job, args) in jobs if job == "send_invite_email"]
    assert len(sends) == 1

    # Re-adding the same email is a duplicate, not a second row/email.
    r = await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": "jordan@apitest.dev", "first_name": "J", "last_name": "L"}],
    )
    assert r.json()["added"] == 0 and r.json()["duplicates"] == 1


async def test_draft_requisition_queues_emails_until_deploy(
    client, admin_headers, high_requisition_cap, jobs
):
    req = await deploy_requisition(client, admin_headers, deploy=False, invite_only=True)
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": f"q-{uuid.uuid4().hex[:6]}@apitest.dev", "first_name": "Q", "last_name": "D"}],
    )
    assert not [1 for (job, _) in jobs if job == "send_invite_email"]

    # Deploying releases the queued invite emails.
    from tests.api.conftest import builder_payload

    r = await client.put(
        f"/api/admin/console/requisitions/{req['id']}",
        json=builder_payload(deploy=True, title=req["title"], invite_only=True),
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert [1 for (job, _) in jobs if job == "send_invite_email"]


async def test_csv_and_xlsx_import(client, admin_headers, high_requisition_cap, jobs):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    csv_body = (
        "email,first name,last name\n"
        f"csv-{uuid.uuid4().hex[:6]}@apitest.dev,Csv,Row\n"
        "broken-row,Nope,\n"
    ).encode()
    r = await client.post(
        f"{_invites_url(req['id'])}/import",
        files={"file": ("candidates.csv", csv_body, "text/csv")},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1
    # 1-based file rows (header included) so the reporter can find the line.
    assert r.json()["invalid"] == [{"row": 3, "reason": "invalid email"}]

    wb = Workbook()
    wb.active.append(["Email", "First Name", "Last Name"])
    wb.active.append([f"xlsx-{uuid.uuid4().hex[:6]}@apitest.dev", "Xlsx", "Row"])
    buf = io.BytesIO()
    wb.save(buf)
    r = await client.post(
        f"{_invites_url(req['id'])}/import",
        files={
            "file": (
                "candidates.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1

    r = await client.post(
        f"{_invites_url(req['id'])}/import",
        files={"file": ("notes.txt", b"nope", "text/plain")},
        headers=admin_headers,
    )
    assert r.status_code == 422


async def test_resend_requeues_email(client, admin_headers, high_requisition_cap, jobs):
    req = await deploy_requisition(client, admin_headers, invite_only=True)
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": f"rs-{uuid.uuid4().hex[:6]}@apitest.dev", "first_name": "R", "last_name": "S"}],
    )
    invites = (await client.get(_invites_url(req["id"]), headers=admin_headers)).json()
    before = len([1 for (job, _) in jobs if job == "send_invite_email"])
    r = await client.post(
        f"{_invites_url(req['id'])}/{invites[0]['id']}/resend", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert len([1 for (job, _) in jobs if job == "send_invite_email"]) == before + 1


# --------------------------------------------------------------------------- #
# the send_invite_email job end-to-end (console transport)
# --------------------------------------------------------------------------- #
async def test_send_invite_email_job_delivers_and_stamps_status(
    client, admin_headers, high_requisition_cap, jobs, monkeypatch
):
    from app.core import email as email_core
    from app.core.config import settings
    from app.jobs.email import send_invite_email

    monkeypatch.setattr(settings, "email_transport", "console")
    email_core._transports.clear()
    email_core.OUTBOX.clear()

    req = await deploy_requisition(client, admin_headers, invite_only=True, end_date="2026-07-31")
    email = f"job-{uuid.uuid4().hex[:6]}@apitest.dev"
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": email, "first_name": "Jordan", "last_name": "Lee"}],
    )
    async with SessionLocal() as db:
        invite = (
            await db.execute(select(RequisitionInvite).where(RequisitionInvite.email == email))
        ).scalar_one()

    await send_invite_email({"job_try": 1}, str(invite.id))

    (captured,) = email_core.OUTBOX
    assert captured["to"] == email
    assert f"/i/{req['invite_token']}" in captured["html"]
    assert "Hi Jordan," in captured["text"]
    assert "July 31, 2026" in captured["text"]
    async with SessionLocal() as db:
        refreshed = await db.get(RequisitionInvite, invite.id)
        assert refreshed.email_status == "sent"
        assert refreshed.last_emailed_at is not None


async def test_unknown_requisition_invites_404(client, admin_headers):
    """The guest list rides _get_live_requisition: unknown (or another org's)
    requisition ids 404 without leaking existence."""
    r = await client.get(_invites_url(str(new_id())), headers=admin_headers)
    assert r.status_code == 404


async def test_completed_application_shows_in_invite_status(
    client,
    admin_headers,
    candidate_headers,
    service_headers,
    high_requisition_cap,
    jobs,
    livekit_creds,
    stub_object_storage,
    candidate,
):
    """Full path: invited → claimed → completed reflected in the console list."""
    from tests.api.test_interview_lifecycle import _insert_ready_plan, _upload_selfie

    req = await deploy_requisition(client, admin_headers, invite_only=True)
    await _add(
        client,
        admin_headers,
        req["id"],
        [{"email": candidate.email, "first_name": "Full", "last_name": "Path"}],
    )
    claim = await client.post(
        f"/api/candidate/i/{req['invite_token']}/claim", headers=candidate_headers
    )
    assert claim.status_code == 200, claim.text
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
    for status in ({"status": "live"}, {"status": "ended", "end_reason": "completed"}):
        r = await client.post(
            f"/internal/interviews/{interview_id}/status", json=status, headers=service_headers
        )
        assert r.status_code == 200, r.text

    invites = (await client.get(_invites_url(req["id"]), headers=admin_headers)).json()
    assert invites[0]["email"] == candidate.email.lower()
    assert invites[0]["status"] == "completed"
