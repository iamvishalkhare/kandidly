"""add_end_date

Revision ID: 0004_add_end_date
Revises: 0003_orgs_console
Create Date: 2026-07-07 01:44:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004_add_end_date'
down_revision: Union[str, None] = '0003_orgs_console'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('requisitions', sa.Column('end_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('requisitions', 'end_date')
