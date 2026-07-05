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
    QuestionPlanOut,
    ReportDraft,
    ResumeParsed,
    TurnAnnotationOut,
)


def ensure_provider_env() -> None:
    """Bridge KANDIDLY_-prefixed provider keys to the plain env vars the
    provider SDKs (and pydantic-ai) read. Raises a friendly error when the
    required key for the configured model is absent."""
    import os

    from app.core.errors import AppError

    mapping = {
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "OPENAI_API_KEY": settings.openai_api_key,
        "GOOGLE_API_KEY": settings.google_api_key,
    }
    for var, value in mapping.items():
        if value and not os.environ.get(var):
            os.environ[var] = value

    if not (settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")):
        raise AppError(
            "not_ready",
            "LLM provider not configured — set KANDIDLY_ANTHROPIC_API_KEY in infra/.env "
            "and restart the stack",
            status_code=503,
        )


def _make_agent(model: str, output_type: Any, system_prompt: str):
    """Construct a pydantic-ai Agent. Kept in one place so the [VERIFY-DOC]
    keyword names (`output_type`/`result_type`) are adjusted once."""
    from pydantic_ai import Agent  # lazy import

    ensure_provider_env()
    try:
        return Agent(model, output_type=output_type, system_prompt=system_prompt)
    except TypeError:
        # Older pydantic-ai used `result_type`.
        return Agent(model, result_type=output_type, system_prompt=system_prompt)  # type: ignore


@lru_cache
def resume_extractor():
    return _make_agent(settings.extract_llm, ResumeParsed, load_prompt("extract", "v1"))


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
