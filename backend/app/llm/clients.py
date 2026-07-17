"""pydantic-ai agent factories, one per non-realtime LLM role (SPEC §3.3, §3.1).

[VERIFY-DOC] The pydantic-ai surface (Agent constructor, `result_type` vs
`output_type`, run methods, TestModel/FunctionModel) MUST be confirmed against
the installed version — the documented API wins over this sketch (SPEC §0.2).
Import of pydantic_ai is lazy so unit tests that inject TestModel don't require
provider keys, and so importing this module never fails when the SDK differs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.llm.prompts import load_prompt
from app.llm.schemas import (
    CriterionScoreOut,
    IntegrityReviewOut,
    QuestionPlanOut,
    ReportDraft,
    SnapshotBatchOut,
    SourceDigest,
    TurnAnnotationOut,
)

# Maps a `provider:model` prefix to the plain env var the provider SDK reads and
# the corresponding KANDIDLY_-prefixed setting. Prefixes are what pydantic-ai's
# model-string inference accepts (SPEC §3.3).
_PROVIDER_ENV: dict[str, tuple[str, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
    "google": ("GOOGLE_API_KEY", "google_api_key"),
    "google-gla": ("GOOGLE_API_KEY", "google_api_key"),
    "google-vertex": ("GOOGLE_API_KEY", "google_api_key"),
    "openrouter": ("OPENROUTER_API_KEY", "openrouter_api_key"),
}


def ensure_provider_env(model: str) -> None:
    """Bridge the KANDIDLY_-prefixed key for `model`'s provider to the plain env
    var the provider SDK (and pydantic-ai) reads. Raises a friendly error when
    that key is absent. Unknown prefixes (e.g. `test:`) are left to pydantic-ai."""
    import os

    from app.core.errors import AppError

    provider = model.split(":", 1)[0]
    entry = _PROVIDER_ENV.get(provider)
    if entry is None:
        return
    env_var, setting_name = entry
    value = getattr(settings, setting_name, "")
    if value and not os.environ.get(env_var):
        os.environ[env_var] = value

    if not os.environ.get(env_var):
        raise AppError(
            "not_ready",
            f"LLM provider '{provider}' not configured — set KANDIDLY_{env_var} "
            "in infra/.env and restart the stack",
            status_code=503,
        )


def _make_agent(model: str, output_type: Any, system_prompt: str):
    """Construct a pydantic-ai Agent. Kept in one place so the [VERIFY-DOC]
    keyword names (`output_type`/`result_type`) are adjusted once."""
    from pydantic_ai import Agent  # lazy import

    ensure_provider_env(model)
    try:
        return Agent(model, output_type=output_type, system_prompt=system_prompt)
    except TypeError:
        # Older pydantic-ai used `result_type`.
        return Agent(model, result_type=output_type, system_prompt=system_prompt)  # type: ignore


@lru_cache
def source_summarizer():
    return _make_agent(settings.extract_llm, SourceDigest, load_prompt("enrich", "v1"))


@lru_cache
def plan_generator():
    return _make_agent(settings.plan_llm, QuestionPlanOut, load_prompt("plan", "v1"))


@lru_cache
def evidence_annotator():
    return _make_agent(
        settings.annotate_llm, list[TurnAnnotationOut], load_prompt("annotate", "v1")
    )


@lru_cache
def rubric_scorer():
    # Realtime scoring goes through the Batch API (SPEC §11.3); this single-shot
    # agent is used for the E15 individual-retry fallback and for tests.
    return _make_agent(settings.score_llm, CriterionScoreOut, load_prompt("score", "v1"))


@lru_cache
def report_writer():
    return _make_agent(settings.report_llm, ReportDraft, load_prompt("report", "v1"))


@lru_cache
def proctor_vision():
    # Vision-capable model; called with [text, BinaryContent(image/webp), …]
    # batches by jobs/proctor_vision.py. PromptedOutput (JSON-by-instruction)
    # instead of the default tool-calling mode: OpenRouter's vision endpoints
    # (e.g. qwen2.5-vl) often ship without tool support and 404 otherwise.
    from pydantic_ai import PromptedOutput  # lazy import

    return _make_agent(
        settings.vision_llm,
        PromptedOutput(SnapshotBatchOut),
        load_prompt("proctor_vision", "v1"),
    )


@lru_cache
def integrity_reviewer():
    # Text-only: turns the accumulated per-frame analyses into the final
    # 0-100 integrity score (jobs/proctor_vision.review_integrity).
    return _make_agent(settings.integrity_llm, IntegrityReviewOut, load_prompt("integrity", "v1"))
