"""console_allowlist

Global invite-only gate for console sign-in: only emails in this table (plus
the hardcoded operator, domain/access.py) can complete a console-intent WorkOS
login. Candidate sign-ins are unaffected. Starts empty on purpose — the
operator hardcode is the bootstrap.

Revision ID: 0011_console_allowlist
Revises: 0010_requisition_invites
Create Date: 2026-07-19 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011_console_allowlist"
down_revision: str | None = "0010_requisition_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "console_allowlist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("added_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("console_allowlist")
