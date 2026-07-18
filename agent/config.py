"""Agent worker config from env (SPEC §6.1). Minimal — the agent only needs a
subset of settings."""

from __future__ import annotations

import os


class AgentConfig:
    backend_url = os.environ.get("KANDIDLY_BACKEND_URL", "http://localhost:8000")
    service_token = os.environ.get("KANDIDLY_SERVICE_TOKEN", "dev-service-token-change-me")
    redis_url = os.environ.get("KANDIDLY_REDIS_URL", "redis://localhost:6379/0")

    livekit_url = os.environ.get("KANDIDLY_LIVEKIT_URL", "")
    livekit_api_key = os.environ.get("KANDIDLY_LIVEKIT_API_KEY", "")
    livekit_api_secret = os.environ.get("KANDIDLY_LIVEKIT_API_SECRET", "")
    # Explicit named dispatch — dev and prod share one LiveKit project, so an
    # unnamed worker (automatic dispatch) steals the other env's interview
    # jobs. Must match the backend's KANDIDLY_LIVEKIT_AGENT_NAME (it embeds
    # this name in the candidate's room token).
    livekit_agent_name = os.environ.get("KANDIDLY_LIVEKIT_AGENT_NAME", "kandidly-dev")

    deepgram_api_key = os.environ.get("KANDIDLY_DEEPGRAM_API_KEY", "")
    cartesia_api_key = os.environ.get("KANDIDLY_CARTESIA_API_KEY", "")
    anthropic_api_key = os.environ.get("KANDIDLY_ANTHROPIC_API_KEY", "")

    realtime_llm = os.environ.get("KANDIDLY_REALTIME_LLM", "anthropic:claude-haiku-4-5")
    stt = os.environ.get("KANDIDLY_STT", "deepgram:nova-3")
    tts = os.environ.get("KANDIDLY_TTS", "cartesia:sonic")
    tts_voice = os.environ.get("KANDIDLY_TTS_VOICE", "")

    max_interview_seconds = int(os.environ.get("KANDIDLY_MAX_INTERVIEW_SECONDS", "1800"))
    wrap_trigger_seconds = int(os.environ.get("KANDIDLY_WRAP_TRIGGER_SECONDS", "180"))
    max_concurrent = int(os.environ.get("KANDIDLY_AGENT_MAX_CONCURRENT", "50"))


config = AgentConfig()
