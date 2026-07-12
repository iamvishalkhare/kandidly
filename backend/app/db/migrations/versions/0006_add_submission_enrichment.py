"""add_submission_enrichment

Durable store for scraped candidate sources (GitHub / website / blog) assembled
into the interview context bundle at form submit.

Revision ID: 0006_add_submission_enrichment
Revises: 0005_allow_zero_weight
Create Date: 2026-07-09 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0006_add_submission_enrichment'
down_revision: Union[str, None] = '0005_allow_zero_weight'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'form_submissions',
        sa.Column(
            'enrichment',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        'form_submissions',
        sa.Column(
            'enrichment_status',
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.create_check_constraint(
        'enrichment_status_valid',
        'form_submissions',
        "enrichment_status IN ('pending','processing','done','failed','skipped')",
    )


def downgrade() -> None:
    op.drop_constraint('enrichment_status_valid', 'form_submissions', type_='check')
    op.drop_column('form_submissions', 'enrichment_status')
    op.drop_column('form_submissions', 'enrichment')
