"""SQLAlchemy models mirroring SPEC §7 verbatim. Column/table names are
normative (SPEC §0.5). Enum-likes are text + CHECK (SPEC D16). UUIDv7 PKs are
generated in app code (see app.core.ids.new_id) — do not rely on DB defaults.

NOTE: `users` and `organizations` are owned by THIS database (supersedes the
SPEC §3.6 external-auth assumption). WorkOS integration later syncs into them
via users.workos_user_id / organizations.workos_org_id; auth remains an
external-JWT contract (app.core.security).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    # PK value supplied by application code (app.core.ids.new_id); no server default.
    return mapped_column(UUID(as_uuid=True), primary_key=True)


def _ts_created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# --------------------------------------------------------------------------- #
# Organizations & users (locally owned; WorkOS-synced later via workos_* ids)
# --------------------------------------------------------------------------- #
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    workos_org_id: Mapped[str | None] = mapped_column(Text, unique=True)
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts_created()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # org membership is for staff (admin/recruiter); candidates stay org-less.
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    workos_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'active'"))
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("role IN ('admin','recruiter','candidate')", name="role_valid"),
        CheckConstraint("status IN ('active','invited','suspended')", name="status_valid"),
        Index("ix_users_org", "org_id"),
    )


# --------------------------------------------------------------------------- #
# 7.1 Generic file registry
# --------------------------------------------------------------------------- #
class StoredFile(Base):
    __tablename__ = "stored_files"
    id: Mapped[uuid.UUID] = _uuid_pk()
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (UniqueConstraint("bucket", "key", name="bucket_key"),)


# --------------------------------------------------------------------------- #
# 7.2 Form templates (immutable versions)
# --------------------------------------------------------------------------- #
class FormTemplate(Base):
    __tablename__ = "form_templates"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    interview_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    field_hints: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'draft'"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = _ts_created()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','published','archived')", name="template_status_valid"),
        UniqueConstraint("family_id", "version", name="template_family_version"),
        Index("ix_form_templates_family", "family_id", desc("version")),
        Index("ix_form_templates_org", "org_id"),
    )


class Rubric(Base):
    __tablename__ = "rubrics"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    interview_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'draft'"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = _ts_created()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','published','archived')", name="rubric_status_valid"),
        UniqueConstraint("family_id", "version", name="rubric_family_version"),
        Index("ix_rubrics_org", "org_id"),
    )


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    id: Mapped[uuid.UUID] = _uuid_pk()
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    level_anchors: Mapped[list] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        CheckConstraint("weight >= 0", name="weight_positive"),
        UniqueConstraint("rubric_id", "key", name="rubric_key"),
    )


# --------------------------------------------------------------------------- #
# 7.4 Requisitions
# --------------------------------------------------------------------------- #
class Requisition(Base):
    __tablename__ = "requisitions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # Human-readable code (e.g. REQ-0001) — server-generated from
    # requisition_code_seq, never client-supplied.
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text)
    technical_requirements: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa_text("'{}'")
    )
    role_objective: Mapped[str | None] = mapped_column(Text)
    # Ordered list of {"id","text"} — edited as a whole in the builder.
    sample_questions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'[]'::jsonb")
    )
    interview_type: Mapped[str] = mapped_column(Text, nullable=False)
    form_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_templates.id"), nullable=False
    )
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'draft'"))
    interview_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Soft delete: hidden from every admin/console read, invite links stop
    # resolving (status flips to 'closed'), but interviews keep their FK and
    # stay fully viewable in the ledger. Never hard-deleted.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','open','paused','closed')", name="status_valid"),
        UniqueConstraint("org_id", "code", name="requisition_org_code"),
        Index("ix_requisitions_org", "org_id"),
        Index("ix_requisitions_domain", "domain"),
        Index("ix_requisitions_skills", "technical_requirements", postgresql_using="gin"),
    )


# --------------------------------------------------------------------------- #
# 7.5 Invite links
# --------------------------------------------------------------------------- #
class InviteLink(Base):
    __tablename__ = "invite_links"
    id: Mapped[uuid.UUID] = _uuid_pk()
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requisitions.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    # Landing-page resolves of the link (use_count counts claims).
    click_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("0"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("kind IN ('open','personal')", name="kind_valid"),
        CheckConstraint("kind <> 'personal' OR email IS NOT NULL", name="personal_needs_email"),
        Index("ix_invite_links_req", "requisition_id"),
    )


class RequisitionInvite(Base):
    """Guest list for invite-only requisitions (interview_config.invite_only).
    Not a token: every candidate uses the requisition's single open invite
    link — claim just checks the authenticated email against this list.
    email is stored lowercased+trimmed; uninvite sets revoked_at (row kept
    for audit, blocks future claims only)."""

    __tablename__ = "requisition_invites"
    id: Mapped[uuid.UUID] = _uuid_pk()
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requisitions.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    # candidate_invite delivery: queued (not yet handed to Resend — e.g. the
    # requisition is still a draft) | sent | failed (terminal send failure).
    email_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sa_text("'queued'")
    )
    last_emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        UniqueConstraint("requisition_id", "email", name="uq_requisition_invite_email"),
        CheckConstraint(
            "email_status IN ('queued','sent','failed')", name="ck_invite_email_status"
        ),
        Index("ix_invites_requisition", "requisition_id"),
    )


# --------------------------------------------------------------------------- #
# 7.6 Applications
# --------------------------------------------------------------------------- #
class Application(Base):
    __tablename__ = "applications"
    id: Mapped[uuid.UUID] = _uuid_pk()
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requisitions.id"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    invite_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invite_links.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'registered'"))
    state_timestamps: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    # FKs added post-hoc in the SPEC DDL (ALTER TABLE after the referenced
    # tables exist). use_alter breaks the create-order cycle for metadata DDL.
    form_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("form_submissions.id", use_alter=True, name="fk_app_form"),
        nullable=True,
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", use_alter=True, name="fk_app_interview"),
        nullable=True,
    )
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('registered','form_in_progress','form_submitted','plan_ready',"
            "'in_lobby','in_interview','completed','scored','reviewed','abandoned','expired')",
            name="state_valid",
        ),
        Index(
            "uq_app_live",
            "requisition_id",
            "candidate_id",
            unique=True,
            postgresql_where=sa_text("state NOT IN ('abandoned','expired')"),
        ),
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(Text)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("actor IN ('candidate','system','admin','agent')", name="actor_valid"),
        Index("ix_app_events_app", "application_id", "created_at"),
    )


# --------------------------------------------------------------------------- #
# 7.7 Form submissions
# --------------------------------------------------------------------------- #
class FormSubmission(Base):
    __tablename__ = "form_submissions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, unique=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_templates.id"), nullable=False
    )
    answers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    resume_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=True
    )
    # Resume as Markdown (converted locally, no LLM) — the sole resume representation
    # fed to the plan generator and live interviewer (both LLMs). resume_parsed is
    # deprecated (kept nullable for back-compat; no longer written).
    resume_markdown: Mapped[str | None] = mapped_column(Text)
    resume_parsed: Mapped[dict | None] = mapped_column(JSONB)
    resume_parse_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sa_text("'pending'")
    )
    # Scraped GitHub / website / blog sources (SPEC §8.6 enrichment). Shape:
    # {"sources": [{"kind","url","status","digest"|"text","fetched_at"}]}.
    enrichment: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    enrichment_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=sa_text("'pending'")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts_created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "resume_parse_status IN ('pending','processing','done','failed','skipped')",
            name="parse_status_valid",
        ),
        CheckConstraint(
            "enrichment_status IN ('pending','processing','done','failed','skipped')",
            name="enrichment_status_valid",
        ),
        Index("ix_form_sub_answers", "answers", postgresql_using="gin"),
    )


# --------------------------------------------------------------------------- #
# 7.8 Consents
# --------------------------------------------------------------------------- #
class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    recording_ack: Mapped[bool] = mapped_column(Boolean, nullable=False)
    monitoring_ack: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("recording_ack AND monitoring_ack", name="both_acks_required"),
    )


# --------------------------------------------------------------------------- #
# 7.9 Interviews
# --------------------------------------------------------------------------- #
class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[uuid.UUID] = _uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False, unique=True
    )
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requisitions.id"), nullable=False
    )
    # Human-readable code (e.g. INT-1001) from interview_code_seq; always set
    # by app code at creation, nullable only for DDL simplicity.
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'created'"))
    room_name: Mapped[str | None] = mapped_column(Text, unique=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_active_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa_text("0")
    )
    end_reason: Mapped[str | None] = mapped_column(Text)
    audio_recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=True
    )
    # Precomputed player peaks: {"version":1,"peaks":[0..100 ints],"bins":N,
    # "duration_seconds":N}. The recording itself lives in S3.
    audio_waveform: Mapped[dict | None] = mapped_column(JSONB)
    # Final LLM integrity verdict over the analyzed proctor frames
    # (jobs/proctor_vision.review_integrity): 0-100 score, higher = cleaner,
    # plus {summary, band, model, prompt_version, frames_reviewed, generated_at}.
    integrity_score: Mapped[int | None] = mapped_column(Integer)
    integrity_review: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint(
            "status IN ('created','lobby','live','paused','wrap_up','ended','finalized')",
            name="status_valid",
        ),
        CheckConstraint(
            "end_reason IN ('completed','time_cap','abandoned','error','admin_terminated')",
            name="end_reason_valid",
        ),
    )


# --------------------------------------------------------------------------- #
# 7.10 Question plans
# --------------------------------------------------------------------------- #
class QuestionPlan(Base):
    __tablename__ = "question_plans"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by_model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    total_budget_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("status IN ('ready','fallback_generic','failed')", name="status_valid"),
    )


class QuestionPlanNode(Base):
    __tablename__ = "question_plan_nodes"
    id: Mapped[uuid.UUID] = _uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_plans.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    node_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    seed_question: Mapped[str] = mapped_column(Text, nullable=False)
    target_criteria: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa_text("'{}'")
    )
    difficulty: Mapped[int | None] = mapped_column(Integer)
    soft_budget_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    max_followups: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sa_text("2"))
    provenance: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'pending'"))
    skip_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('intro','topic','candidate_questions','wrap','injected')",
            name="node_type_valid",
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),
        CheckConstraint("state IN ('pending','active','done','skipped')", name="state_valid"),
        UniqueConstraint("plan_id", "position", name="plan_position"),
    )


# --------------------------------------------------------------------------- #
# 7.11 Turns
# --------------------------------------------------------------------------- #
class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_plan_nodes.id"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stt_confidence: Mapped[float | None] = mapped_column(REAL)
    decision: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    __table_args__ = (
        CheckConstraint("speaker IN ('kandidly','candidate','system')", name="speaker_valid"),
        CheckConstraint(
            "decision IN ('GREET','ASK','PROBE','CLARIFY','ADVANCE','WRAP','CLOSE')",
            name="decision_valid",
        ),
        UniqueConstraint("interview_id", "seq", name="interview_seq"),
        Index("ix_turns_interview", "interview_id", "seq"),
    )


# --------------------------------------------------------------------------- #
# 7.12 Evidence notes
# --------------------------------------------------------------------------- #
class EvidenceNote(Base):
    __tablename__ = "evidence_notes"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("turns.id"), nullable=False
    )
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    signal: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint(
            "signal IN ('strong_positive','positive','neutral','negative',"
            "'strong_negative','unclear')",
            name="signal_valid",
        ),
        Index("ix_evidence_interview", "interview_id", "criterion_key"),
    )


# --------------------------------------------------------------------------- #
# 7.13 Observer injections
# --------------------------------------------------------------------------- #
class Injection(Base):
    __tablename__ = "injections"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'queued'"))
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_plan_nodes.id"), nullable=True
    )
    created_at: Mapped[datetime] = _ts_created()
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('queued','asked','discarded')", name="status_valid"),
    )


# --------------------------------------------------------------------------- #
# 7.14 Proctoring
# --------------------------------------------------------------------------- #
class ProctoringEvent(Base):
    __tablename__ = "proctoring_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    server_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint("source IN ('browser','audio','video_meta','system')", name="source_valid"),
        CheckConstraint("severity IN ('info','low','medium','high')", name="severity_valid"),
        Index("ix_proctor_interview", "interview_id", "server_ts"),
    )


class ProctoringSnapshot(Base):
    __tablename__ = "proctoring_snapshots"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    faces_detected: Mapped[int | None] = mapped_column(Integer)
    face_present: Mapped[bool | None] = mapped_column(Boolean)
    client_meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    analyzed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    # Analysis verdict shown on the review page; set by the snapshot-analysis
    # job (or seed), not derived at read time.
    signal: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "signal IN ('clear','attention_shift','low_light','no_face','multiple_faces')",
            name="signal_valid",
        ),
        Index("ix_snapshots_interview", "interview_id", "captured_at"),
    )


class IdentityCheck(Base):
    __tablename__ = "identity_checks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True
    )
    reference_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'pending'"))
    sampled_count: Mapped[int | None] = mapped_column(Integer)
    match_rate: Mapped[float | None] = mapped_column(REAL)
    min_similarity: Mapped[float | None] = mapped_column(REAL)
    verdict: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','done','failed')", name="status_valid"),
        CheckConstraint(
            "verdict IN ('consistent','inconsistent','insufficient')", name="verdict_valid"
        ),
    )


# --------------------------------------------------------------------------- #
# 7.15 Scoring
# --------------------------------------------------------------------------- #
class ScoringJob(Base):
    __tablename__ = "scoring_jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'queued'"))
    provider_batch_id: Mapped[str | None] = mapped_column(Text)
    runs_requested: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa_text("3")
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts_created()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','submitted','polling','aggregating','done','failed')",
            name="status_valid",
        ),
    )


class CriterionScore(Base):
    __tablename__ = "criterion_scores"
    id: Mapped[uuid.UUID] = _uuid_pk()
    scoring_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scoring_jobs.id", ondelete="CASCADE"), nullable=False
    )
    run_index: Mapped[int] = mapped_column(Integer, nullable=False)
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 5", name="score_range"),
        UniqueConstraint("scoring_job_id", "run_index", "criterion_key", name="job_run_criterion"),
    )


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False
    )
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    # 0–100 scale; LLM runs score 1–5 anchors (criterion_scores) and are
    # converted at aggregation (app.domain.scoring.anchor_to_score100).
    final_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'median'"))
    disagreement: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint("final_score BETWEEN 0 AND 100", name="final_score_range"),
        UniqueConstraint("interview_id", "criterion_key", name="interview_criterion"),
    )


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = _uuid_pk()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True
    )
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # 0–100
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False)
    concerns: Mapped[list] = mapped_column(JSONB, nullable=False)
    coverage: Mapped[list] = mapped_column(JSONB, nullable=False)
    proctoring_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'draft'"))
    reviewed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    review_decision: Mapped[str | None] = mapped_column(Text)
    html_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=True
    )
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("status IN ('draft','final')", name="status_valid"),
        CheckConstraint("overall_score BETWEEN 0 AND 100", name="overall_score_range"),
        CheckConstraint(
            "review_decision IN ('shortlist','reject','hold')", name="review_decision_valid"
        ),
    )


# --------------------------------------------------------------------------- #
# 7.16 Audit log
# --------------------------------------------------------------------------- #
class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),)


# --------------------------------------------------------------------------- #
# Catalog entries — autocomplete sources for the requisition builder
# (domains / skills / job titles). Values on requisitions stay denormalized
# strings; catalog rows are suggestions, not FK targets.
# --------------------------------------------------------------------------- #
class CatalogEntry(Base):
    __tablename__ = "catalog_entries"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = _ts_created()
    __table_args__ = (
        CheckConstraint("kind IN ('domain','skill','job_title')", name="kind_valid"),
        UniqueConstraint("org_id", "kind", "value", name="org_kind_value"),
        Index("ix_catalog_org_kind", "org_id", "kind"),
    )
