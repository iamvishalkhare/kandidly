"""add_resume_markdown

Store the resume as Markdown (converted locally from PDF/DOCX, no LLM) — the sole
resume representation fed to the plan generator and live interviewer, both of which
are LLMs. Supersedes the structured resume_parsed JSON, which is left in place but
no longer written.

Revision ID: 0007_add_resume_markdown
Revises: 0006_add_submission_enrichment
Create Date: 2026-07-10 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007_add_resume_markdown'
down_revision: Union[str, None] = '0006_add_submission_enrichment'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'form_submissions',
        sa.Column('resume_markdown', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('form_submissions', 'resume_markdown')
