"""Free-plan quota gates (app/domain/plan.py): the console deploy cap and the
candidate-side interview hold (ER0402). Counts are monkeypatched so the gates
are exercised without a database."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.domain import plan


def _fixed_count(value: int):
    async def _count(db, org_id):
        return value

    return _count


# --------------------------------------------------------------------------- #
# deploy gate
# --------------------------------------------------------------------------- #
async def test_deploy_allowed_under_limit(monkeypatch):
    monkeypatch.setattr(
        plan, "requisition_count", _fixed_count(settings.free_plan_max_requisitions - 1)
    )
    await plan.ensure_can_create_requisition(None, uuid4(), deploy=True)  # no raise


async def test_deploy_blocked_at_limit(monkeypatch):
    monkeypatch.setattr(
        plan, "requisition_count", _fixed_count(settings.free_plan_max_requisitions)
    )
    with pytest.raises(AppError) as exc:
        await plan.ensure_can_create_requisition(None, uuid4(), deploy=True)
    assert exc.value.code == "plan_limit"
    assert exc.value.status_code == 402
    assert exc.value.message == "Please upgrade to deploy more interviews."


async def test_draft_save_blocked_at_limit_with_plain_message(monkeypatch):
    monkeypatch.setattr(
        plan, "requisition_count", _fixed_count(settings.free_plan_max_requisitions + 3)
    )
    with pytest.raises(AppError) as exc:
        await plan.ensure_can_create_requisition(None, uuid4(), deploy=False)
    assert exc.value.code == "plan_limit"
    assert "upgrade" in exc.value.message.lower()


# --------------------------------------------------------------------------- #
# candidate hold (ER0402)
# --------------------------------------------------------------------------- #
async def test_interview_capacity_open_under_threshold(monkeypatch):
    monkeypatch.setattr(
        plan, "interview_count", _fixed_count(settings.free_plan_interview_hold_at - 1)
    )
    await plan.ensure_interview_capacity(None, uuid4())  # no raise


async def test_interview_capacity_hold_at_threshold(monkeypatch):
    monkeypatch.setattr(
        plan, "interview_count", _fixed_count(settings.free_plan_interview_hold_at)
    )
    with pytest.raises(AppError) as exc:
        await plan.ensure_interview_capacity(None, uuid4())
    assert exc.value.code == "plan_limit"
    assert exc.value.status_code == 402
    assert exc.value.detail["error_code"] == "ER0402"
    assert exc.value.message == (
        "This interview is on hold. Please contact your recruiter for more details."
    )
