"""initial schema (SPEC §7)

Revision ID: 0001_initial
Revises: 0000_users
Create Date: 2026-07-05

Explicit DDL for every SPEC §7 table, frozen from the SQLAlchemy models
(previously emitted live via Base.metadata.create_all — frozen so later
migrations can evolve the models without changing what a fresh migrate
creates). The applications → form_submissions/interviews FK cycle is
resolved by adding fk_app_form / fk_app_interview via ALTER TABLE at the
end of upgrade(); the models mark these use_alter, and inline emission in
create_table would be silently skipped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = "0000_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_log_actor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_table(
        "form_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("interview_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "field_hints",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')",
            name=op.f("ck_form_templates_template_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_form_templates_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form_templates")),
        sa.UniqueConstraint("family_id", "version", name="template_family_version"),
    )
    op.create_index(
        "ix_form_templates_family",
        "form_templates",
        ["family_id", sa.literal_column("version DESC")],
        unique=False,
    )
    op.create_table(
        "rubrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("interview_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')",
            name=op.f("ck_rubrics_rubric_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_rubrics_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubrics")),
        sa.UniqueConstraint("family_id", "version", name="rubric_family_version"),
    )
    op.create_table(
        "stored_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_stored_files_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
        sa.UniqueConstraint("bucket", "key", name="bucket_key"),
    )
    op.create_table(
        "requisitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("interview_type", sa.Text(), nullable=False),
        sa.Column("form_template_id", sa.UUID(), nullable=False),
        sa.Column("rubric_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column(
            "interview_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','open','paused','closed')",
            name=op.f("ck_requisitions_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_requisitions_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["form_template_id"],
            ["form_templates.id"],
            name=op.f("fk_requisitions_form_template_id_form_templates"),
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"], ["rubrics.id"], name=op.f("fk_requisitions_rubric_id_rubrics")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requisitions")),
    )
    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rubric_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("level_anchors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("weight > 0", name=op.f("ck_rubric_criteria_weight_positive")),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_rubric_criteria_rubric_id_rubrics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_criteria")),
        sa.UniqueConstraint("rubric_id", "key", name="rubric_key"),
    )
    op.create_table(
        "invite_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requisition_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind <> 'personal' OR email IS NOT NULL",
            name=op.f("ck_invite_links_personal_needs_email"),
        ),
        sa.CheckConstraint("kind IN ('open','personal')", name=op.f("ck_invite_links_kind_valid")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_invite_links_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["requisitions.id"],
            name=op.f("fk_invite_links_requisition_id_requisitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invite_links")),
        sa.UniqueConstraint("token", name=op.f("uq_invite_links_token")),
    )
    op.create_index("ix_invite_links_req", "invite_links", ["requisition_id"], unique=False)
    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("requisition_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("invite_link_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'registered'"), nullable=False),
        sa.Column(
            "state_timestamps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("form_submission_id", sa.UUID(), nullable=True),
        sa.Column("interview_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('registered','form_in_progress','form_submitted','plan_ready',"
            "'in_lobby','in_interview','completed','scored','reviewed','abandoned','expired')",
            name=op.f("ck_applications_state_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["users.id"], name=op.f("fk_applications_candidate_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["invite_link_id"],
            ["invite_links.id"],
            name=op.f("fk_applications_invite_link_id_invite_links"),
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["requisitions.id"],
            name=op.f("fk_applications_requisition_id_requisitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    op.create_index(
        "uq_app_live",
        "applications",
        ["requisition_id", "candidate_id"],
        unique=True,
        postgresql_where=sa.text("state NOT IN ('abandoned','expired')"),
    )
    op.create_table(
        "application_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor IN ('candidate','system','admin','agent')",
            name=op.f("ck_application_events_actor_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_events_application_id_applications"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(
        "ix_app_events_app", "application_events", ["application_id", "created_at"], unique=False
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("consent_version", sa.Text(), nullable=False),
        sa.Column("recording_ack", sa.Boolean(), nullable=False),
        sa.Column("monitoring_ack", sa.Boolean(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "recording_ack AND monitoring_ack", name=op.f("ck_consents_both_acks_required")
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_consents_application_id_applications"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_consents_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
        sa.UniqueConstraint("application_id", name=op.f("uq_consents_application_id")),
    )
    op.create_table(
        "form_submissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("resume_file_id", sa.UUID(), nullable=True),
        sa.Column("resume_parsed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "resume_parse_status", sa.Text(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "resume_parse_status IN ('pending','processing','done','failed','skipped')",
            name=op.f("ck_form_submissions_parse_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_form_submissions_application_id_applications"),
        ),
        sa.ForeignKeyConstraint(
            ["resume_file_id"],
            ["stored_files.id"],
            name=op.f("fk_form_submissions_resume_file_id_stored_files"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["form_templates.id"],
            name=op.f("fk_form_submissions_template_id_form_templates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form_submissions")),
        sa.UniqueConstraint("application_id", name=op.f("uq_form_submissions_application_id")),
    )
    op.create_index(
        "ix_form_sub_answers", "form_submissions", ["answers"], unique=False, postgresql_using="gin"
    )
    op.create_table(
        "interviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("requisition_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'created'"), nullable=False),
        sa.Column("room_name", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "elapsed_active_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("audio_recording_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_reason IN ('completed','time_cap','abandoned','error','admin_terminated')",
            name=op.f("ck_interviews_end_reason_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('created','lobby','live','paused','wrap_up','ended','finalized')",
            name=op.f("ck_interviews_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_interviews_application_id_applications"),
        ),
        sa.ForeignKeyConstraint(
            ["audio_recording_id"],
            ["stored_files.id"],
            name=op.f("fk_interviews_audio_recording_id_stored_files"),
        ),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["requisitions.id"],
            name=op.f("fk_interviews_requisition_id_requisitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
        sa.UniqueConstraint("application_id", name=op.f("uq_interviews_application_id")),
        sa.UniqueConstraint("room_name", name=op.f("uq_interviews_room_name")),
    )
    op.create_table(
        "evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("final_score", sa.Numeric(precision=3, scale=1), nullable=False),
        sa.Column("method", sa.Text(), server_default=sa.text("'median'"), nullable=False),
        sa.Column("disagreement", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["interviews.id"], name=op.f("fk_evaluations_interview_id_interviews")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluations")),
        sa.UniqueConstraint("interview_id", "criterion_key", name="interview_criterion"),
    )
    op.create_table(
        "identity_checks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("reference_file_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("sampled_count", sa.Integer(), nullable=True),
        sa.Column("match_rate", sa.REAL(), nullable=True),
        sa.Column("min_similarity", sa.REAL(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','done','failed')",
            name=op.f("ck_identity_checks_status_valid"),
        ),
        sa.CheckConstraint(
            "verdict IN ('consistent','inconsistent','insufficient')",
            name=op.f("ck_identity_checks_verdict_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_identity_checks_interview_id_interviews"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_file_id"],
            ["stored_files.id"],
            name=op.f("fk_identity_checks_reference_file_id_stored_files"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_checks")),
        sa.UniqueConstraint("interview_id", name=op.f("uq_identity_checks_interview_id")),
    )
    op.create_table(
        "proctoring_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("client_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "server_ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "severity IN ('info','low','medium','high')",
            name=op.f("ck_proctoring_events_severity_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('browser','audio','video_meta','system')",
            name=op.f("ck_proctoring_events_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_proctoring_events_application_id_applications"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_proctoring_events_interview_id_interviews"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proctoring_events")),
    )
    op.create_index(
        "ix_proctor_interview", "proctoring_events", ["interview_id", "server_ts"], unique=False
    )
    op.create_table(
        "proctoring_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("faces_detected", sa.Integer(), nullable=True),
        sa.Column("face_present", sa.Boolean(), nullable=True),
        sa.Column(
            "client_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("analyzed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_files.id"],
            name=op.f("fk_proctoring_snapshots_file_id_stored_files"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_proctoring_snapshots_interview_id_interviews"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proctoring_snapshots")),
    )
    op.create_index(
        "ix_snapshots_interview",
        "proctoring_snapshots",
        ["interview_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "question_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("generated_by_model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("total_budget_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ready','fallback_generic','failed')",
            name=op.f("ck_question_plans_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_question_plans_interview_id_interviews"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_plans")),
        sa.UniqueConstraint("interview_id", name=op.f("uq_question_plans_interview_id")),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("concerns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("proctoring_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("review_decision", sa.Text(), nullable=True),
        sa.Column("html_file_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('draft','final')", name=op.f("ck_reports_status_valid")),
        sa.ForeignKeyConstraint(
            ["html_file_id"], ["stored_files.id"], name=op.f("fk_reports_html_file_id_stored_files")
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["interviews.id"], name=op.f("fk_reports_interview_id_interviews")
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_reports_reviewed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        sa.UniqueConstraint("interview_id", name=op.f("uq_reports_interview_id")),
    )
    op.create_table(
        "scoring_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("provider_batch_id", sa.Text(), nullable=True),
        sa.Column("runs_requested", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','submitted','polling','aggregating','done','failed')",
            name=op.f("ck_scoring_jobs_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_scoring_jobs_interview_id_interviews"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scoring_jobs")),
        sa.UniqueConstraint("interview_id", name=op.f("uq_scoring_jobs_interview_id")),
    )
    op.create_table(
        "criterion_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scoring_job_id", sa.UUID(), nullable=False),
        sa.Column("run_index", sa.Integer(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name=op.f("ck_criterion_scores_score_range")),
        sa.ForeignKeyConstraint(
            ["scoring_job_id"],
            ["scoring_jobs.id"],
            name=op.f("fk_criterion_scores_scoring_job_id_scoring_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_criterion_scores")),
        sa.UniqueConstraint(
            "scoring_job_id", "run_index", "criterion_key", name="job_run_criterion"
        ),
    )
    op.create_table(
        "question_plan_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("node_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("seed_question", sa.Text(), nullable=False),
        sa.Column(
            "target_criteria", sa.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("soft_budget_seconds", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("max_followups", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "node_type IN ('intro','topic','candidate_questions','wrap','injected')",
            name=op.f("ck_question_plan_nodes_node_type_valid"),
        ),
        sa.CheckConstraint(
            "state IN ('pending','active','done','skipped')",
            name=op.f("ck_question_plan_nodes_state_valid"),
        ),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 5", name=op.f("ck_question_plan_nodes_difficulty_range")
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["question_plans.id"],
            name=op.f("fk_question_plan_nodes_plan_id_question_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_plan_nodes")),
        sa.UniqueConstraint("plan_id", "position", name="plan_position"),
    )
    op.create_table(
        "injections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','asked','discarded')", name=op.f("ck_injections_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["interviews.id"], name=op.f("fk_injections_interview_id_interviews")
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["question_plan_nodes.id"],
            name=op.f("fk_injections_node_id_question_plan_nodes"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_injections_requested_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_injections")),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stt_confidence", sa.REAL(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('GREET','ASK','PROBE','CLARIFY','ADVANCE','WRAP','CLOSE')",
            name=op.f("ck_turns_decision_valid"),
        ),
        sa.CheckConstraint(
            "speaker IN ('kandidly','candidate','system')", name=op.f("ck_turns_speaker_valid")
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["interviews.id"], name=op.f("fk_turns_interview_id_interviews")
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["question_plan_nodes.id"],
            name=op.f("fk_turns_node_id_question_plan_nodes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turns")),
        sa.UniqueConstraint("interview_id", "seq", name="interview_seq"),
    )
    op.create_index("ix_turns_interview", "turns", ["interview_id", "seq"], unique=False)
    op.create_table(
        "evidence_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("turn_id", sa.UUID(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "signal IN ('strong_positive','positive','neutral','negative',"
            "'strong_negative','unclear')",
            name=op.f("ck_evidence_notes_signal_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interviews.id"],
            name=op.f("fk_evidence_notes_interview_id_interviews"),
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"], ["turns.id"], name=op.f("fk_evidence_notes_turn_id_turns")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_notes")),
    )
    op.create_index(
        "ix_evidence_interview", "evidence_notes", ["interview_id", "criterion_key"], unique=False
    )
    # Deferred FKs closing the applications ↔ form_submissions/interviews
    # cycle (use_alter in the models; SPEC DDL adds them via ALTER TABLE).
    op.create_foreign_key(
        "fk_app_form", "applications", "form_submissions", ["form_submission_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_app_interview", "applications", "interviews", ["interview_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_app_interview", "applications", type_="foreignkey")
    op.drop_constraint("fk_app_form", "applications", type_="foreignkey")
    op.drop_index("ix_evidence_interview", table_name="evidence_notes")
    op.drop_table("evidence_notes")
    op.drop_index("ix_turns_interview", table_name="turns")
    op.drop_table("turns")
    op.drop_table("injections")
    op.drop_table("question_plan_nodes")
    op.drop_table("criterion_scores")
    op.drop_table("scoring_jobs")
    op.drop_table("reports")
    op.drop_table("question_plans")
    op.drop_index("ix_snapshots_interview", table_name="proctoring_snapshots")
    op.drop_table("proctoring_snapshots")
    op.drop_index("ix_proctor_interview", table_name="proctoring_events")
    op.drop_table("proctoring_events")
    op.drop_table("identity_checks")
    op.drop_table("evaluations")
    op.drop_table("interviews")
    op.drop_index("ix_form_sub_answers", table_name="form_submissions", postgresql_using="gin")
    op.drop_table("form_submissions")
    op.drop_table("consents")
    op.drop_index("ix_app_events_app", table_name="application_events")
    op.drop_table("application_events")
    op.drop_index(
        "uq_app_live",
        table_name="applications",
        postgresql_where=sa.text("state NOT IN ('abandoned','expired')"),
    )
    op.drop_table("applications")
    op.drop_index("ix_invite_links_req", table_name="invite_links")
    op.drop_table("invite_links")
    op.drop_table("rubric_criteria")
    op.drop_table("requisitions")
    op.drop_table("stored_files")
    op.drop_table("rubrics")
    op.drop_index("ix_form_templates_family", table_name="form_templates")
    op.drop_table("form_templates")
    op.drop_table("audit_log")
