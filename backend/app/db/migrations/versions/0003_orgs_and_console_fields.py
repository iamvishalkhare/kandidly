"""organizations + console fields + 0–100 scores

Revision ID: 0003_orgs_console
Revises: 0002_views
Create Date: 2026-07-06

Adds the organizations layer (WorkOS-ready), user profile columns,
requisition/interview console fields (codes, domain, skills, objective,
sample questions, waveform, click counts, proctor signal), the
catalog_entries autocomplete table, and rescales evaluation/report scores
from the 1–5 anchor scale to 0–100 (linear map: score100 = (x-1)/4*100).
The 0–100 downgrade transform is lossy (rounds back to one decimal on the
anchor scale).

v_score_distribution is dropped and recreated because Postgres refuses
ALTER TYPE on a view-referenced column; the new view buckets by decile.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_orgs_console"
down_revision = "0002_views"
branch_labels = None
depends_on = None

# Fixed so backfills here and the seed script agree without a lookup.
DEFAULT_ORG_ID = "01980000-0000-7000-8000-000000000001"
DEFAULT_ORG_SLUG = "kandidly"

V_SCORE_DISTRIBUTION_OLD = """
CREATE VIEW v_score_distribution AS
SELECT i.requisition_id,
       ev.criterion_key,
       ROUND(ev.final_score)::int AS score,
       COUNT(*) AS count
FROM evaluations ev
JOIN interviews i ON i.id = ev.interview_id
GROUP BY i.requisition_id, ev.criterion_key, ROUND(ev.final_score)::int;
"""

V_SCORE_DISTRIBUTION_NEW = """
CREATE VIEW v_score_distribution AS
SELECT i.requisition_id,
       ev.criterion_key,
       (ROUND(ev.final_score / 10) * 10)::int AS score_bucket,
       COUNT(*) AS count
FROM evaluations ev
JOIN interviews i ON i.id = ev.interview_id
GROUP BY i.requisition_id, ev.criterion_key, (ROUND(ev.final_score / 10) * 10)::int;
"""


def upgrade() -> None:
    # --- organizations -------------------------------------------------- #
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("workos_org_id", sa.Text(), nullable=True),
        sa.Column(
            "settings",
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
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.UniqueConstraint("workos_org_id", name="uq_organizations_workos_org_id"),
    )
    op.execute(
        f"INSERT INTO organizations (id, name, slug) "
        f"VALUES ('{DEFAULT_ORG_ID}', 'Kandidly', '{DEFAULT_ORG_SLUG}')"
    )

    # --- users: profile + WorkOS columns -------------------------------- #
    op.add_column("users", sa.Column("org_id", sa.UUID(), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("workos_user_id", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
    )
    op.create_foreign_key(
        "fk_users_org_id_organizations", "users", "organizations", ["org_id"], ["id"]
    )
    op.create_unique_constraint("uq_users_workos_user_id", "users", ["workos_user_id"])
    op.create_check_constraint(
        "ck_users_status_valid", "users", "status IN ('active','invited','suspended')"
    )
    op.create_index("ix_users_org", "users", ["org_id"])
    op.execute(f"UPDATE users SET org_id = '{DEFAULT_ORG_ID}' WHERE role IN ('admin','recruiter')")

    # --- org_id on requisitions / form_templates / rubrics -------------- #
    for table in ("form_templates", "rubrics", "requisitions"):
        op.add_column(table, sa.Column("org_id", sa.UUID(), nullable=True))
        op.execute(f"UPDATE {table} SET org_id = '{DEFAULT_ORG_ID}'")
        op.alter_column(table, "org_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_org_id_organizations", table, "organizations", ["org_id"], ["id"]
        )
        op.create_index(f"ix_{table}_org", table, ["org_id"])

    # --- requisition console fields -------------------------------------- #
    op.execute("CREATE SEQUENCE requisition_code_seq")
    op.add_column("requisitions", sa.Column("code", sa.Text(), nullable=True))
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM requisitions
        )
        UPDATE requisitions r SET code = 'REQ-' || lpad(o.rn::text, 4, '0')
        FROM ordered o WHERE o.id = r.id
        """
    )
    op.execute(
        "SELECT setval('requisition_code_seq', (SELECT count(*) + 1 FROM requisitions), false)"
    )
    op.alter_column("requisitions", "code", nullable=False)
    op.create_unique_constraint("requisition_org_code", "requisitions", ["org_id", "code"])
    op.add_column("requisitions", sa.Column("domain", sa.Text(), nullable=True))
    op.add_column(
        "requisitions",
        sa.Column(
            "technical_requirements",
            sa.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("requisitions", sa.Column("role_objective", sa.Text(), nullable=True))
    op.add_column(
        "requisitions",
        sa.Column(
            "sample_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index("ix_requisitions_domain", "requisitions", ["domain"])
    op.create_index(
        "ix_requisitions_skills",
        "requisitions",
        ["technical_requirements"],
        postgresql_using="gin",
    )

    # --- interviews: code + waveform ------------------------------------- #
    op.execute("CREATE SEQUENCE interview_code_seq START 1001")
    op.add_column("interviews", sa.Column("code", sa.Text(), nullable=True))
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM interviews
        )
        UPDATE interviews i SET code = 'INT-' || (1000 + o.rn)::text
        FROM ordered o WHERE o.id = i.id
        """
    )
    op.execute(
        "SELECT setval('interview_code_seq', (SELECT count(*) + 1001 FROM interviews), false)"
    )
    op.create_unique_constraint("uq_interviews_code", "interviews", ["code"])
    op.add_column(
        "interviews",
        sa.Column("audio_waveform", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # --- invite link click tracking -------------------------------------- #
    op.add_column(
        "invite_links",
        sa.Column("click_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    # --- proctoring snapshot analysis verdict ----------------------------- #
    op.add_column("proctoring_snapshots", sa.Column("signal", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_proctoring_snapshots_signal_valid",
        "proctoring_snapshots",
        "signal IN ('clear','attention_shift','low_light','no_face','multiple_faces')",
    )

    # --- 0–100 score rescale ---------------------------------------------- #
    op.execute("DROP VIEW v_score_distribution")
    op.alter_column(
        "evaluations",
        "final_score",
        type_=sa.Numeric(precision=5, scale=2),
        existing_type=sa.Numeric(precision=3, scale=1),
        existing_nullable=False,
    )
    op.execute("UPDATE evaluations SET final_score = round((final_score - 1) / 4 * 100, 2)")
    op.create_check_constraint(
        "ck_evaluations_final_score_range", "evaluations", "final_score BETWEEN 0 AND 100"
    )
    op.alter_column(
        "reports",
        "overall_score",
        type_=sa.Numeric(precision=5, scale=2),
        existing_type=sa.Numeric(precision=4, scale=2),
        existing_nullable=False,
    )
    op.execute("UPDATE reports SET overall_score = round((overall_score - 1) / 4 * 100, 2)")
    op.create_check_constraint(
        "ck_reports_overall_score_range", "reports", "overall_score BETWEEN 0 AND 100"
    )
    op.execute(V_SCORE_DISTRIBUTION_NEW)

    # --- review decision enum --------------------------------------------- #
    op.execute(
        "UPDATE reports SET review_decision = lower(review_decision) "
        "WHERE review_decision IS NOT NULL"
    )
    op.execute(
        "UPDATE reports SET review_decision = NULL "
        "WHERE review_decision IS NOT NULL "
        "AND review_decision NOT IN ('shortlist','reject','hold')"
    )
    op.create_check_constraint(
        "ck_reports_review_decision_valid",
        "reports",
        "review_decision IN ('shortlist','reject','hold')",
    )

    # --- catalog_entries (builder autocomplete) --------------------------- #
    op.create_table(
        "catalog_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('domain','skill','job_title')", name=op.f("ck_catalog_entries_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_catalog_entries_org_id_organizations")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_catalog_entries_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_entries")),
        sa.UniqueConstraint("org_id", "kind", "value", name="org_kind_value"),
    )
    op.create_index("ix_catalog_org_kind", "catalog_entries", ["org_id", "kind"])

    # --- audit trail lookup index ------------------------------------------ #
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_entity", table_name="audit_log")
    op.drop_index("ix_catalog_org_kind", table_name="catalog_entries")
    op.drop_table("catalog_entries")

    op.drop_constraint("ck_reports_review_decision_valid", "reports", type_="check")

    op.execute("DROP VIEW v_score_distribution")
    op.drop_constraint("ck_reports_overall_score_range", "reports", type_="check")
    # Lossy inverse of the 0–100 rescale (back to one decimal on 1–5).
    op.execute("UPDATE reports SET overall_score = round(overall_score / 100 * 4 + 1, 2)")
    op.alter_column(
        "reports",
        "overall_score",
        type_=sa.Numeric(precision=4, scale=2),
        existing_type=sa.Numeric(precision=5, scale=2),
        existing_nullable=False,
    )
    op.drop_constraint("ck_evaluations_final_score_range", "evaluations", type_="check")
    op.execute("UPDATE evaluations SET final_score = round(final_score / 100 * 4 + 1, 1)")
    op.alter_column(
        "evaluations",
        "final_score",
        type_=sa.Numeric(precision=3, scale=1),
        existing_type=sa.Numeric(precision=5, scale=2),
        existing_nullable=False,
    )
    op.execute(V_SCORE_DISTRIBUTION_OLD)

    op.drop_constraint(
        "ck_proctoring_snapshots_signal_valid", "proctoring_snapshots", type_="check"
    )
    op.drop_column("proctoring_snapshots", "signal")

    op.drop_column("invite_links", "click_count")

    op.drop_column("interviews", "audio_waveform")
    op.drop_constraint("uq_interviews_code", "interviews", type_="unique")
    op.drop_column("interviews", "code")
    op.execute("DROP SEQUENCE interview_code_seq")

    op.drop_index("ix_requisitions_skills", table_name="requisitions")
    op.drop_index("ix_requisitions_domain", table_name="requisitions")
    op.drop_column("requisitions", "sample_questions")
    op.drop_column("requisitions", "role_objective")
    op.drop_column("requisitions", "technical_requirements")
    op.drop_column("requisitions", "domain")
    op.drop_constraint("requisition_org_code", "requisitions", type_="unique")
    op.drop_column("requisitions", "code")
    op.execute("DROP SEQUENCE requisition_code_seq")

    for table in ("requisitions", "rubrics", "form_templates"):
        op.drop_index(f"ix_{table}_org", table_name=table)
        op.drop_constraint(f"fk_{table}_org_id_organizations", table, type_="foreignkey")
        op.drop_column(table, "org_id")

    op.drop_index("ix_users_org", table_name="users")
    op.drop_constraint("ck_users_status_valid", "users", type_="check")
    op.drop_constraint("uq_users_workos_user_id", "users", type_="unique")
    op.drop_constraint("fk_users_org_id_organizations", "users", type_="foreignkey")
    op.drop_column("users", "status")
    op.drop_column("users", "workos_user_id")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")
    op.drop_column("users", "org_id")

    op.drop_table("organizations")
