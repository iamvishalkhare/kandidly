"""allow_zero_weight

Revision ID: 0005_allow_zero_weight
Revises: 0004_add_end_date
Create Date: 2026-07-07 02:50:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0005_allow_zero_weight'
down_revision: Union[str, None] = '0004_add_end_date'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE rubric_criteria DROP CONSTRAINT IF EXISTS ck_rubric_criteria_weight_positive')
    op.execute('ALTER TABLE rubric_criteria ADD CONSTRAINT ck_rubric_criteria_weight_positive CHECK (weight >= 0)')


def downgrade() -> None:
    op.execute('ALTER TABLE rubric_criteria DROP CONSTRAINT IF EXISTS ck_rubric_criteria_weight_positive')
    op.execute('ALTER TABLE rubric_criteria ADD CONSTRAINT ck_rubric_criteria_weight_positive CHECK (weight > 0)')
