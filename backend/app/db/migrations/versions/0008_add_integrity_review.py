"""add_integrity_review

Final LLM integrity verdict per interview (jobs/proctor_vision.review_integrity):
a 0-100 score over the per-frame vision analyses plus the review payload
{summary, band, model, prompt_version, frames_reviewed, generated_at}.

Revision ID: 0008_add_integrity_review
Revises: 0007_add_resume_markdown
Create Date: 2026-07-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_add_integrity_review"
down_revision: str | None = "0007_add_resume_markdown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("integrity_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("integrity_review", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interviews", "integrity_review")
    op.drop_column("interviews", "integrity_score")
