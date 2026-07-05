"""users (external auth table — created locally for FK integrity)

Revision ID: 0000_users
Revises:
Create Date: 2026-07-05

NOTE (SPEC §3.6): the users table is owned by the external auth system. It is
created here so local/dev/CI FKs resolve. In an environment where users already
exists, this migration is a no-op (guarded by checkfirst).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0000_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names():
        return
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("role IN ('admin','recruiter','candidate')", name="ck_users_role_valid"),
    )


def downgrade() -> None:
    op.drop_table("users")
