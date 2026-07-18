"""Ops remediation (ops.yml `reset-scoring`): wipe an interview's scoring
artifacts (scoring job + criterion scores via cascade, evaluations, report)
and re-enqueue run_scoring from scratch. For re-scoring after a scoring-
pipeline fix — unlike `enqueue-scoring`, which no-ops once the job row says
'done' and never re-runs saved criterion scores.

Run inside the backend container:
    env PYTHONPATH=/app/backend /app/.venv/bin/python \
        /app/backend/scripts/reset_scoring.py <interview-uuid>
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID


async def main(interview_id: UUID) -> None:
    from sqlalchemy import delete, select

    from app.core.queue import enqueue
    from app.db.models import Evaluation, Interview, Report, ScoringJob
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None:
            print("interview not found")
            return
        sj = (
            await db.execute(select(ScoringJob).where(ScoringJob.interview_id == interview_id))
        ).scalar_one_or_none()
        if sj is not None:
            # criterion_scores cascade from the scoring job (ondelete=CASCADE).
            await db.execute(delete(ScoringJob).where(ScoringJob.id == sj.id))
        await db.execute(delete(Evaluation).where(Evaluation.interview_id == interview_id))
        await db.execute(delete(Report).where(Report.interview_id == interview_id))
        await db.commit()
    await enqueue("run_scoring", str(interview_id))
    print(f"scoring reset + re-enqueued for {interview_id}")


if __name__ == "__main__":
    asyncio.run(main(UUID(sys.argv[1])))
