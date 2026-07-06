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

    # model matrix (SPEC §3.3)
    realtime_llm: str = "anthropic:claude-haiku-4-5"
    extract_llm: str = "anthropic:claude-sonnet-4-6"
    plan_llm: str = "anthropic:claude-sonnet-4-6"
    annotate_llm: str = "anthropic:claude-haiku-4-5"
    score_llm: str = "anthropic:claude-sonnet-4-6"
    report_llm: str = "anthropic:claude-sonnet-4-6"
    stt: str = "deepgram:nova-3"
    tts: str = "cartesia:sonic"
    tts_voice: str = ""

    # interview tuning
    base_url_web: str = "http://localhost:5173"
    max_interview_seconds: int = 1800
    wrap_trigger_seconds: int = 180
    rejoin_grace_seconds: int = 600
    snapshot_min_s: int = 5
    snapshot_max_s: int = 10
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
