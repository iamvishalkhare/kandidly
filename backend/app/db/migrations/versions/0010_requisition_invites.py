"""requisition_invites

Guest list for invite-only requisitions (interview_config.invite_only, no
schema change there — JSONB). One row per invited email; the requisition's
single open invite link stays the only URL, claim checks the authenticated
candidate's email against this table. Uninvite sets revoked_at.

Revision ID: 0010_requisition_invites
Revises: 0009_add_requisition_deleted_at
Create Date: 2026-07-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0010_requisition_invites"
down_revision: str | None = "0009_add_requisition_deleted_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requisition_invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requisition_id",
            UUID(as_uuid=True),
            sa.ForeignKey("requisitions.id"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("email_status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("last_emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("requisition_id", "email", name="uq_requisition_invite_email"),
        sa.CheckConstraint(
            "email_status IN ('queued','sent','failed')", name="ck_invite_email_status"
        ),
    )
    op.create_index("ix_invites_requisition", "requisition_invites", ["requisition_id"])


def downgrade() -> None:
    op.drop_index("ix_invites_requisition", table_name="requisition_invites")
    op.drop_table("requisition_invites")
