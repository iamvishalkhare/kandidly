"""Structured-output result types for all non-realtime LLM calls (pydantic-ai,
SPEC §3.1, §8.6, §11, §20). These are the `result_type`s bound to each agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Resume extractor — result of extract_v1 (SPEC §8.6.3)
# --------------------------------------------------------------------------- #
class ResumeExperience(BaseModel):
    company: str
    role: str
    start: str | None = None
    end: str | None = None
    highlights: list[str] = Field(default_factory=list)


class ResumeProject(BaseModel):
    name: str
    description: str
    tech: list[str] = Field(default_factory=list)


class NotableClaim(BaseModel):
    claim: str  # verbatim-ish, specific & probe-worthy
    source_section: Literal["experience", "projects", "summary", "other"]


class ResumeParsed(BaseModel):
    full_name: str | None = None
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    notable_claims: list[NotableClaim] = Field(default_factory=list, max_length=10)
    total_experience_years: float | None = None


# --------------------------------------------------------------------------- #
# Plan generator — result of plan_v1 (SPEC §7.10 node fields minus ids/state)
# --------------------------------------------------------------------------- #
NodeType = Literal["intro", "topic", "candidate_questions", "wrap", "injected"]


class Provenance(BaseModel):
    source: str  # e.g. "resume.projects[1]", "form.complex_system", "generic_bank"
    detail: str = ""


class QuestionNodeOut(BaseModel):
    node_type: NodeType
    title: str
    seed_question: str
    target_criteria: list[str] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    soft_budget_seconds: int
    priority: int = Field(ge=1, le=5)
    max_followups: int = 2
    provenance: Provenance = Field(default_factory=lambda: Provenance(source="generic_bank"))


class QuestionPlanOut(BaseModel):
    nodes: list[QuestionNodeOut]


# --------------------------------------------------------------------------- #
# Evidence annotator — result of annotate_v1 (SPEC §20.6)
# --------------------------------------------------------------------------- #
Signal = Literal["strong_positive", "positive", "neutral", "negative", "strong_negative", "unclear"]


class TurnAnnotationOut(BaseModel):
    criterion_key: str
    signal: Signal
    note: str = Field(max_length=200)


# --------------------------------------------------------------------------- #
# Rubric scorer — result of score_v1, per criterion × run (SPEC §11.3)
# --------------------------------------------------------------------------- #
class EvidenceQuote(BaseModel):
    turn_id: str
    quote: str


class CriterionScoreOut(BaseModel):
    score: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceQuote] = Field(default_factory=list)
    rationale: str


# --------------------------------------------------------------------------- #
# Report writer — result of report_v1 (SPEC §11.5, §20.5)
# --------------------------------------------------------------------------- #
class ReportDraft(BaseModel):
    summary: str
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
