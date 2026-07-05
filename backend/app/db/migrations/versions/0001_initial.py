"""initial schema (SPEC §7)

Revision ID: 0001_initial
Revises: 0000_users
Create Date: 2026-07-05

Creates every SPEC §7 table from the SQLAlchemy models, which mirror the
normative DDL exactly (SPEC §0.5, §7). Emitting from metadata (rather than
hand-writing 25 create_table calls) keeps the migration and models provably in
sync; the models are the single source of truth.
"""

from __future__ import annotations

from alembic import op

from app.db import models  # noqa: F401 — register all tables on Base.metadata
from app.db.base import Base

revision = "0001_initial"
down_revision = "0000_users"
branch_labels = None
depends_on = None


def _spec_tables():
    # Everything except the externally-owned users table (created in 0000).
    return [t for t in Base.metadata.sorted_tables if t.name != "users"]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=_spec_tables(), checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=_spec_tables(), checkfirst=False)
