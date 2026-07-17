"""arq worker settings (SPEC §3.1, §14). `arq app.jobs.worker.WorkerSettings`."""

from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.jobs.annotate import annotate_turn
from app.jobs.enrichment import enrich_sources
from app.jobs.interviews import (
    aggregate_scores,
    build_report,
    finalize_interview,
    identity_check,
    poll_batches,
    refresh_summary,
    run_scoring,
)
from app.jobs.planning import generate_plan
from app.jobs.proctor_vision import analyze_snapshots, review_integrity
from app.jobs.recording import process_recording
from app.jobs.resume import parse_resume
from app.jobs.sweepers import retention_sweeper, sweep_abandoned, sweep_links_and_apps


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 50
    # analyze_snapshots at the 180-frame ceiling is ~30 vision calls with a
    # retry each — comfortably under 900s, not always under 600s. run_scoring
    # is criteria × runs × attempts LLM calls, each now capped at 90s
    # (interviews.py) — 1800s gives a degraded-provider run room to finish,
    # because a job killed by this timeout is failed for good, never retried.
    job_timeout = 1800

    functions = [
        parse_resume,
        enrich_sources,
        generate_plan,
        annotate_turn,
        finalize_interview,
        run_scoring,
        aggregate_scores,
        build_report,
        identity_check,
        refresh_summary,
        process_recording,
        analyze_snapshots,
        review_integrity,
    ]

    cron_jobs = [
        cron(poll_batches, second={0}),  # every 60s
        cron(sweep_abandoned, second={30}),  # every 60s, offset
        cron(sweep_links_and_apps, hour={3}, minute={0}),  # daily
        cron(retention_sweeper, hour={4}, minute={0}),  # daily
    ]
