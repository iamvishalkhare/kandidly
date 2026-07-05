/**
 * TypeScript types mirroring the Pydantic schemas in backend/app/schemas/api.py
 */

// --- Public ---
export interface ConfigOut {
  snapshot_min_s: number;
  snapshot_max_s: number;
  livekit_url: string;
}

export interface LinkResolveOut {
  title: string | null;
  interview_type: string | null;
  status_ok: boolean;
  reason: string | null;
}

// --- Candidate ---
export interface ClaimOut {
  application_id: string;
  state: string;
}

export interface ApplicationOut {
  id: string;
  requisition_id: string;
  state: string;
  state_timestamps: Record<string, string>;
  interview_id: string | null;
  template_schema: FormSchema | null;
  answers: Record<string, unknown> | null;
  resume_parse_status: string | null;
}

export interface FormSchema {
  type: string;
  properties: Record<string, FormFieldSchema>;
  required?: string[];
  'x-kandidly'?: {
    field_order?: string[];
  };
}

export interface FormFieldSchema {
  type?: string;
  title?: string;
  description?: string;
  maxLength?: number;
  minLength?: number;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  items?: { enum?: string[] };
  'x-field'?: string; // short_text | long_text | single_select | multi_select | scale | number | boolean | file
  'x-label'?: string;
  'x-placeholder'?: string;
}

export interface FormPatchIn {
  answers_partial: Record<string, unknown>;
}

export interface FormSubmitOut {
  interview_id: string;
}

export interface ConsentIn {
  consent_version: string;
  recording_ack: boolean;
  monitoring_ack: boolean;
}

export interface JoinOut {
  livekit_url: string;
  token: string;
  room_name: string;
}

// --- Admin: Form Templates ---
export interface FormTemplateOut {
  id: string;
  family_id: string;
  version: number;
  interview_type: string;
  title: string;
  schema: Record<string, unknown>;
  field_hints: Record<string, unknown>;
  status: 'draft' | 'published';
  created_at: string;
  published_at: string | null;
}

// --- Admin: Rubrics ---
export interface LevelAnchor {
  level: number;
  anchor: string;
}

export interface RubricCriterion {
  key: string;
  name: string;
  description: string;
  weight: number;
  display_order: number;
  level_anchors: LevelAnchor[];
}

export interface RubricOut {
  id: string;
  family_id: string;
  version: number;
  interview_type: string;
  title: string;
  status: 'draft' | 'published';
  criteria: RubricCriterion[];
}

// --- Admin: Requisitions & Links ---
export interface RequisitionOut {
  id: string;
  title: string;
  interview_type: string;
  form_template_id: string;
  rubric_id: string;
  status: 'draft' | 'open' | 'paused' | 'closed';
  interview_config: Record<string, unknown>;
  opens_at: string | null;
  closes_at: string | null;
}

export interface LinkOut {
  id: string;
  token: string;
  kind: 'open' | 'personal';
  url: string;
}

// --- Admin: Applications ---
export interface AdminApplicationListOut {
  id: string;
  candidate_name: string;
  candidate_email: string;
  state: string;
  created_at: string;
  overall_score: number | null;
}

export interface AdminApplicationDetailOut {
  id: string;
  requisition_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  state: string;
  state_timestamps: Record<string, string>;
  form_answers: Record<string, unknown> | null;
  interview_id: string | null;
  interview_status: string | null;
  overall_score: number | null;
}

// --- Admin: Transcript ---
export interface TurnOut {
  id: string;
  seq: number;
  speaker: string; // 'kandidly' | 'candidate' | 'system'
  text: string;
  started_at: string;
  ended_at: string | null;
}

export interface TranscriptOut {
  interview_id: string;
  turns: TurnOut[];
}

// --- Admin: Reports ---
export interface EvaluationOut {
  criterion_key: string;
  final_score: number;
  evidence: string[];
  rationale: string;
}

export interface ReportOut {
  id: string;
  interview_id: string;
  overall_score: number;
  summary: string;
  strengths: string[];
  concerns: string[];
  coverage: string[];
  status: string;
  evaluations: EvaluationOut[];
  review_decision: string | null;
  review_notes: string | null;
}

// --- Admin: Funnel ---
export interface FunnelStageOut {
  state: string;
  count: number;
}

export interface FunnelOut {
  stages: FunnelStageOut[];
}

// --- Dev users ---
export interface DevUser {
  email: string;
  role: string;
  token: string;
}

// --- API Error ---
export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

// Application states (ordered)
export const APPLICATION_STATES = [
  'registered',
  'form_in_progress',
  'form_submitted',
  'plan_ready',
  'in_lobby',
  'in_interview',
  'completed',
  'scored',
  'reviewed',
] as const;

export type ApplicationState = typeof APPLICATION_STATES[number];
