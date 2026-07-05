"""Dev seed data (SPEC §18.4). Idempotent: safe to run repeatedly.

Creates: admin + recruiter + 2 candidate users; a published swe_backend KYI
template (8 fields incl. the §8.1.2 examples) + published rubric (5 criteria,
weights 30/25/20/15/10, full anchors); one open requisition + open link. The
generic fallback plan bank lives at app/domain/fallback_plans/swe_backend.json.

Run:  python -m app.db.seed
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.ids import new_id
from app.db.models import (
    FormTemplate,
    InviteLink,
    Requisition,
    Rubric,
    RubricCriterion,
    User,
)
from app.db.session import SessionLocal
from app.domain.links import generate_token
from app.schemas.interview_config import InterviewConfig

TEMPLATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "x-kandidly": {
        "profile": "kyi-form/v1",
        "field_order": [
            "full_name",
            "current_role",
            "years_python",
            "kafka_rating",
            "domains",
            "complex_system",
            "open_source",
            "resume",
        ],
    },
    "required": ["full_name", "resume"],
    "properties": {
        "full_name": {
            "type": "string",
            "title": "Full name",
            "maxLength": 120,
            "x-field": "short_text",
        },
        "current_role": {
            "type": "string",
            "title": "Current role / title",
            "maxLength": 120,
            "x-field": "short_text",
        },
        "years_python": {
            "type": "integer",
            "title": "Years of Python experience",
            "minimum": 0,
            "maximum": 40,
            "x-field": "number",
        },
        "kafka_rating": {
            "type": "integer",
            "title": "Rate your Kafka proficiency",
            "minimum": 1,
            "maximum": 5,
            "x-field": "scale",
        },
        "domains": {
            "type": "array",
            "title": "Domains you have worked in",
            "items": {"enum": ["payments", "healthcare", "ecommerce", "other"]},
            "x-field": "multi_select",
        },
        "complex_system": {
            "type": "string",
            "title": "Describe the most complex system you built",
            "maxLength": 2000,
            "x-field": "long_text",
        },
        "open_source": {
            "type": "boolean",
            "title": "Do you contribute to open source?",
            "x-field": "boolean",
        },
        "resume": {
            "type": "string",
            "title": "Upload your resume",
            "x-field": "file",
            "x-accept": [".pdf", ".docx"],
            "x-max-bytes": 10485760,
        },
    },
}

FIELD_HINTS = {
    "kafka_rating": {
        "use_in_plan": True,
        "role": "difficulty_signal",
        "maps_to_criteria": ["distributed_systems"],
    },
    "complex_system": {
        "use_in_plan": True,
        "role": "seed_topic",
        "maps_to_criteria": ["system_design_depth", "ownership"],
    },
    "domains": {"use_in_plan": True, "role": "context"},
    "years_python": {"use_in_plan": True, "role": "difficulty_signal"},
    "full_name": {"use_in_plan": False},
}


def _anchors(a1, a2, a3, a4, a5):
    return [
        {"level": 1, "anchor": a1},
        {"level": 2, "anchor": a2},
        {"level": 3, "anchor": a3},
        {"level": 4, "anchor": a4},
        {"level": 5, "anchor": a5},
    ]


RUBRIC_CRITERIA = [
    (
        "system_design_depth",
        "System design depth",
        "Depth and soundness of architectural reasoning.",
        30,
        1,
        _anchors(
            "No structure.",
            "Names components only.",
            "Reasonable design, few tradeoffs.",
            "Solid design with explicit tradeoffs.",
            "Excellent; anticipates failure modes.",
        ),
    ),
    (
        "distributed_systems",
        "Distributed systems",
        "Consistency, failure handling, scaling.",
        25,
        2,
        _anchors(
            "No awareness.",
            "Buzzwords only.",
            "Basic correct notions.",
            "Concrete mechanisms explained.",
            "Deep, example-grounded mastery.",
        ),
    ),
    (
        "ownership",
        "Ownership & scope",
        "Personal responsibility and end-to-end ownership.",
        20,
        3,
        _anchors(
            "Peripheral role.",
            "Contributed small parts.",
            "Owned a component.",
            "Owned a system end-to-end.",
            "Drove org-level outcomes.",
        ),
    ),
    (
        "problem_solving",
        "Problem solving",
        "Debugging rigor and structured reasoning.",
        15,
        4,
        _anchors(
            "Gives up.",
            "Trial and error.",
            "Systematic approach.",
            "Strong hypothesis-driven debugging.",
            "Exceptional first-principles reasoning.",
        ),
    ),
    (
        "communication",
        "Communication",
        "Clarity and structure of spoken explanation.",
        10,
        5,
        _anchors(
            "Incoherent.",
            "Hard to follow.",
            "Clear enough.",
            "Clear and well-structured.",
            "Crisp, precise, audience-aware.",
        ),
    ),
]


async def _get_or_create_user(db, email: str, role: str) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing
    user = User(id=new_id(), email=email, role=role)
    db.add(user)
    await db.flush()
    return user


def _dev_token(user: User) -> str:
    payload = {"user_id": str(user.id), "email": user.email, "role": user.role}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


async def seed() -> None:
    async with SessionLocal() as db:
        admin = await _get_or_create_user(db, "admin@kandidly.dev", "admin")
        recruiter = await _get_or_create_user(db, "recruiter@kandidly.dev", "recruiter")
        cand1 = await _get_or_create_user(db, "candidate1@kandidly.dev", "candidate")
        cand2 = await _get_or_create_user(db, "candidate2@kandidly.dev", "candidate")

        # Already seeded?
        existing_req = (
            await db.execute(
                select(Requisition).where(Requisition.title == "Backend Engineer (Seed)")
            )
        ).scalar_one_or_none()
        if existing_req is not None:
            await db.commit()
            _print_creds(admin, recruiter, cand1, cand2, None)
            return

        now = datetime.now(UTC)
        template = FormTemplate(
            id=new_id(),
            family_id=new_id(),
            version=1,
            interview_type="swe_backend",
            title="Backend Engineer KYI",
            schema=TEMPLATE_SCHEMA,
            field_hints=FIELD_HINTS,
            status="published",
            created_by=admin.id,
            published_at=now,
        )
        db.add(template)

        rubric = Rubric(
            id=new_id(),
            family_id=new_id(),
            version=1,
            interview_type="swe_backend",
            title="Backend Engineer Rubric",
            status="published",
            created_by=admin.id,
            published_at=now,
        )
        db.add(rubric)
        await db.flush()
        for key, name, desc, weight, order, anchors in RUBRIC_CRITERIA:
            db.add(
                RubricCriterion(
                    id=new_id(),
                    rubric_id=rubric.id,
                    key=key,
                    name=name,
                    description=desc,
                    weight=weight,
                    display_order=order,
                    level_anchors=anchors,
                )
            )

        req = Requisition(
            id=new_id(),
            title="Backend Engineer (Seed)",
            interview_type="swe_backend",
            form_template_id=template.id,
            rubric_id=rubric.id,
            status="open",
            interview_config=InterviewConfig().model_dump(),
            created_by=admin.id,
        )
        db.add(req)
        await db.flush()

        link = InviteLink(
            id=new_id(),
            requisition_id=req.id,
            token=generate_token(),
            kind="open",
            created_by=admin.id,
        )
        db.add(link)
        await db.commit()
        _print_creds(admin, recruiter, cand1, cand2, link.token)


def _print_creds(admin, recruiter, cand1, cand2, token) -> None:
    print("\n=== Kandidly dev seed ===")
    for u in (admin, recruiter, cand1, cand2):
        print(f"{u.role:10s} {u.email:28s} dev-token: {_dev_token(u)}")
    if token:
        print(f"\nopen invite link token: {token}")
        print(f"landing: /i/{token}")
    print("Use dev tokens as `Authorization: Bearer <token>` with AUTH_DEV_MODE=true.\n")


if __name__ == "__main__":
    asyncio.run(seed())
