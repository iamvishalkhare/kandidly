"""Pydantic request/response models for the REST API (SPEC §12)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.interview_config import InterviewConfig


# --- public (SPEC §12.2) ---------------------------------------------------
class ConfigOut(BaseModel):
    snapshot_interval_s: int
    livekit_url: str
    # Empty when reCAPTCHA is not configured; the client then skips the challenge.
    recaptcha_site_key: str = ""


class LinkResolveOut(BaseModel):
    title: str | None = None
    interview_type: str | None = None
    status_ok: bool
    reason: str | None = None


# --- candidate (SPEC §12.2) ------------------------------------------------
class ClaimOut(BaseModel):
    application_id: UUID
    state: str


class ApplicationOut(BaseModel):
    id: UUID
    requisition_id: UUID
    state: str
    state_timestamps: dict
    interview_id: UUID | None = None
    template_schema: dict | None = None
    answers: dict | None = None
    resume_parse_status: str | None = None
    # Per-requisition proctoring toggle — the lobby skips the camera/selfie
    # step (and its permission prompt) when False.
    proctoring_enabled: bool = True


class FormPatchIn(BaseModel):
    answers_partial: dict = Field(default_factory=dict)


class FormSubmitOut(BaseModel):
    interview_id: UUID


class ConsentIn(BaseModel):
    consent_version: str
    recording_ack: bool
    monitoring_ack: bool


class RecordingCompleteIn(BaseModel):
    """Browser signals the recording is fully uploaded (SPEC §6.3 recordings)."""

    chunks: int = Field(ge=0)
    started_at: datetime
    mime: str = "audio/webm"


class ProctoringJoinOut(BaseModel):
    """Requisition-resolved proctoring settings the interview page acts on:
    no snapshot loop (and no camera prompt) unless enabled."""

    enabled: bool
    snapshot_interval_s: int


class JoinOut(BaseModel):
    livekit_url: str
    token: str
    room_name: str
    proctoring: ProctoringJoinOut


# --- admin: form templates -------------------------------------------------
class FormTemplateCreate(BaseModel):
    interview_type: str
    title: str
    schema: dict  # type: ignore
    field_hints: dict = Field(default_factory=dict)


class FormTemplateOut(BaseModel):
    id: UUID
    family_id: UUID
    version: int
    interview_type: str
    title: str
    schema: dict  # type: ignore
    field_hints: dict
    status: str
    created_at: datetime
    published_at: datetime | None = None


# --- admin: rubrics --------------------------------------------------------
class LevelAnchor(BaseModel):
    level: int = Field(ge=1, le=5)
    anchor: str


class RubricCriterionIn(BaseModel):
    key: str
    name: str
    description: str
    weight: float
    display_order: int
    level_anchors: list[LevelAnchor]


class RubricCreate(BaseModel):
    interview_type: str
    title: str
    criteria: list[RubricCriterionIn]


class RubricOut(BaseModel):
    id: UUID
    family_id: UUID
    version: int
    interview_type: str
    title: str
    status: str
    criteria: list[RubricCriterionIn]


# --- admin: requisitions & links -------------------------------------------
class SampleQuestion(BaseModel):
    id: str
    text: str


class RequisitionCreate(BaseModel):
    title: str
    interview_type: str
    form_template_id: UUID
    rubric_id: UUID
    domain: str | None = None
    technical_requirements: list[str] = []
    role_objective: str | None = None
    sample_questions: list[SampleQuestion] = []
    interview_config: InterviewConfig | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class RequisitionOut(BaseModel):
    id: UUID
    code: str
    title: str
    interview_type: str
    domain: str | None = None
    technical_requirements: list[str] = []
    role_objective: str | None = None
    sample_questions: list[SampleQuestion] = []
    form_template_id: UUID
    rubric_id: UUID
    status: str
    interview_config: dict
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class RequisitionStatusIn(BaseModel):
    status: str


class LinkCreate(BaseModel):
    kind: str
    email: str | None = None
    max_uses: int | None = None
    expires_at: datetime | None = None


class LinkOut(BaseModel):
    id: UUID
    token: str
    kind: str
    url: str


class InjectionIn(BaseModel):
    question_text: str = Field(max_length=400)


# --- admin: applications ---
class AdminApplicationListOut(BaseModel):
    id: UUID
    candidate_name: str
    candidate_email: str
    state: str
    created_at: datetime
    overall_score: float | None = None


class AdminApplicationDetailOut(BaseModel):
    id: UUID
    requisition_id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    state: str
    state_timestamps: dict
    form_answers: dict | None = None
    interview_id: UUID | None = None
    interview_status: str | None = None
    overall_score: float | None = None


# --- admin: transcript ---
class TurnOut(BaseModel):
    id: UUID
    seq: int
    speaker: str
    text: str
    started_at: datetime
    ended_at: datetime | None = None


class TranscriptOut(BaseModel):
    interview_id: UUID
    turns: list[TurnOut]


# --- admin: reports ---
class EvaluationOut(BaseModel):
    criterion_key: str
    final_score: float
    evidence: list
    rationale: str


class ReportOut(BaseModel):
    id: UUID
    interview_id: UUID
    overall_score: float
    summary: str
    strengths: list
    concerns: list
    coverage: list
    status: str
    evaluations: list[EvaluationOut]
    review_decision: str | None = None
    review_notes: str | None = None


class ReportReviewIn(BaseModel):
    decision: Literal["shortlist", "reject", "hold"]
    notes: str | None = None


# --- admin: funnel ---
class FunnelStageOut(BaseModel):
    state: str
    count: int


class FunnelOut(BaseModel):
    stages: list[FunnelStageOut]
