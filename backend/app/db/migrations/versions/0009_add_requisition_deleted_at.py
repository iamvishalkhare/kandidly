"""add_requisition_deleted_at

Soft-delete marker for requisitions (console Delete Requisition). Deleted
requisitions disappear from admin/console reads and their invite links stop
resolving, but interviews taken against them keep their requisition_id and
remain viewable in the ledger.

Revision ID: 0009_add_requisition_deleted_at
Revises: 0008_add_integrity_review
Create Date: 2026-07-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_requisition_deleted_at"
down_revision: str | None = "0008_add_integrity_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "requisitions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("requisitions", "deleted_at")
