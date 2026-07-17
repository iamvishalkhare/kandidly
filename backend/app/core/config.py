"""Application configuration (SPEC §6.1). All settings load from env with the
`KANDIDLY_` prefix via pydantic-settings. Names are normative (SPEC §0.5)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KANDIDLY_",
        env_file=(".env", "../infra/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # core
    env: str = "dev"
    # Deployed commit — injected by deploy.sh via compose (GIT_SHA); surfaced on
    # /healthz so CI can confirm the box actually serves the new build.
    git_sha: str = ""

    # datastores
    database_url: str = "postgresql+asyncpg://kandidly:kandidly@localhost:5432/kandidly"
    redis_url: str = "redis://localhost:6379/0"

    # object store
    s3_endpoint: str = "http://localhost:9000"
    # Browser-reachable endpoint for presigned URLs (empty → same as s3_endpoint)
    s3_public_endpoint: str = ""
    s3_access_key: str = "kandidly"
    s3_secret_key: str = "kandidly-secret"
    s3_region: str = "us-east-1"

    # auth contract (SPEC §3.6)
    jwt_public_key: str = ""
    jwt_alg: str = "RS256"
    auth_dev_mode: bool = False

    # tenancy — slug of the org that new staff/content falls back to until
    # WorkOS org sync lands (must match the org seeded by migration 0003)
    default_org_slug: str = "kandidly"

    # internal service auth (SPEC §12.4)
    service_token: str = "dev-service-token-change-me"

    # free-plan quotas. Deploying past the requisition cap is blocked in the
    # console; once the org's cumulative interview count reaches the hold
    # threshold, candidate attempts are refused with ER0402.
    free_plan_max_requisitions: int = 5
    free_plan_max_interviews: int = 25
    free_plan_interview_hold_at: int = 50

    # revoked-token TTL for the logout denylist (dev tokens never expire on
    # their own, so revocations must outlive any realistic session)
    auth_revoked_token_ttl_s: int = 30 * 24 * 3600

    # captcha — Google reCAPTCHA v3, guards the candidate form submit against
    # bot/DDoS abuse. Empty secret → verification is skipped (dev parity with the
    # fail-open rate limiter); set both keys in prod to enforce.
    recaptcha_site_key: str = ""
    recaptcha_secret_key: str = ""
    recaptcha_min_score: float = 0.5

    # source scraping (interview context enrichment) — optional GitHub token
    # lifts the unauthenticated REST rate limit (60→5000/hr). Empty is fine in dev.
    github_token: str = ""

    # LiveKit
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # providers
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    # OpenRouter — OpenAI-compatible gateway used for the non-realtime LLM roles
    # below (pydantic-ai OpenRouterProvider reads OPENROUTER_API_KEY).
    openrouter_api_key: str = ""

    # model matrix (SPEC §3.3). Non-realtime roles run through pydantic-ai and are
    # served via OpenRouter (`openrouter:<model>`). The realtime role is handled by
    # the LiveKit agent's own inference gateway, not pydantic-ai — leave as-is.
    realtime_llm: str = "anthropic:claude-haiku-4-5"
    extract_llm: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    plan_llm: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    annotate_llm: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    score_llm: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    report_llm: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    # Vision analysis of proctoring snapshots (jobs/proctor_vision.py). Must be
    # a vision-capable model; without an OpenRouter key frames stay pending.
    vision_llm: str = "openrouter:qwen/qwen2.5-vl-72b-instruct"
    # Every captured frame is analyzed (no sampling); this is a cost-safety
    # ceiling per interview = 30 min at the 10s default snapshot_interval_s.
    vision_max_frames: int = 180
    vision_batch_size: int = 6  # frames per LLM call
    # Final integrity verdict over the per-frame analyses (text-only role).
    integrity_llm: str = "openrouter:qwen/qwen3-30b-a3b-instruct-2507"
    stt: str = "deepgram:nova-3"
    tts: str = "cartesia:sonic"
    tts_voice: str = ""

    # interview tuning
    base_url_web: str = "http://localhost:5173"
    max_interview_seconds: int = 1800
    wrap_trigger_seconds: int = 180
    rejoin_grace_seconds: int = 600
    # Proctoring webcam capture cadence — one frame every N seconds.
    snapshot_interval_s: int = 10
    scoring_runs: int = 3
    agent_max_concurrent: int = 50
    retention_days_snapshots: int = 180
    retention_days_audio: int = 365

    # consent version presented in lobby (SPEC §7.8)
    consent_version: str = "v1-2026-07"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
