/**
 * Console API client: typed wrappers over /api/admin/console plus mappers
 * from the backend's snake_case wire shapes into the UI-facing interfaces
 * the console pages already render (Requisition, InterviewRecord, …).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type { Requisition } from '../pages/console/requisitionData';
import type {
  InterviewDecision,
  InterviewReview,
  ProctorFrame,
  RubricAssessment,
  ScoringStatus,
  TranscriptTurn,
} from '../pages/console/interviewData';

/* ── wire types (mirror backend/app/api/console.py) ───────────────────────── */

export interface BuilderFieldWire {
  id: string;
  type: 'text' | 'textarea' | 'multiple_choice' | 'multi_select' | 'range' | 'date' | 'file' | 'social';
  label: string;
  placeholder: string;
  required: boolean;
  options: string[];
}

export interface BuilderCriterionWire {
  id: string;
  name: string;
  description: string;
  weight: number;
}

export interface BuilderQuestionWire {
  id: string;
  text: string;
}

export interface ConsoleRequisitionWire {
  id: string;
  code: string;
  title: string;
  domain: string | null;
  technical_requirements: string[];
  status: string;
  live: boolean;
  opens_at: string | null;
  closes_at: string | null;
  created_at: string;
  invite_token: string | null;
  clicks: number;
  completed: number;
}

export interface ConsoleRequisitionDetailWire extends ConsoleRequisitionWire {
  objective: string | null;
  tone: string;
  sample_questions: BuilderQuestionWire[];
  screening_fields: BuilderFieldWire[];
  rubric: BuilderCriterionWire[];
}

export interface ConsoleRequisitionIn {
  title: string;
  domain: string;
  objective: string;
  skills: string[];
  tone: string;
  sample_questions: BuilderQuestionWire[];
  screening_fields: BuilderFieldWire[];
  rubric: BuilderCriterionWire[];
  deploy: boolean;
}

export interface CatalogWire {
  domains: string[];
  skills: string[];
  job_titles: string[];
}

export interface ConsoleInterviewWire {
  id: string;
  code: string | null;
  candidate_name: string;
  requisition_code: string;
  requisition_title: string;
  domain: string | null;
  scoring_status: 'evaluating' | 'done';
  decision: string | null;
  concluded_at: string | null;
  duration_seconds: number;
  final_score: number | null;
}

export interface ConsoleReviewWire extends ConsoleInterviewWire {
  recommendation: string | null;
  review_decision: string | null;
  assessment_summary: string | null;
  review_notes: string | null;
  percentile: number | null;
  comparison_scores: number[];
  audio_url: string | null;
  waveform: { peaks: number[]; bins: number; duration_seconds: number } | null;
  transcript: { id: string; seconds: number; speaker: string; text: string }[];
  rubric: { key: string; label: string; weight: number; score: number; summary: string; reasoning: string }[];
  proctor_frames: { id: string; seconds: number; signal: string | null; image_url: string | null }[];
  review_trail: { at: string; actor: string; action: string; detail: string | null }[];
}

export interface WeeklyPointWire {
  week_start: string;
  count: number;
}

export interface ConsoleDashboardWire {
  completed_total: number;
  completed_delta_pct: number | null;
  average_score: number | null;
  active_requisitions: number;
  domain_count: number;
  weekly_completed: WeeklyPointWire[];
  weekly_dropped: WeeklyPointWire[];
  recent_interviews: ConsoleInterviewWire[];
}

/* ── mappers into the UI shapes ───────────────────────────────────────────── */

function formatDate(iso: string | null): string {
  if (!iso) return 'N/A';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
}

function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

const DECISION_LABELS: Record<string, InterviewDecision> = {
  shortlist: 'Shortlist',
  hold: 'Hold',
  reject: 'Reject',
};

const SIGNAL_LABELS: Record<string, ProctorFrame['signal']> = {
  clear: 'Clear',
  attention_shift: 'Attention shift',
  low_light: 'Low light',
  no_face: 'No face',
  multiple_faces: 'Multiple faces',
};

export function toRequisition(wire: ConsoleRequisitionWire): Requisition {
  return {
    id: wire.id,
    code: wire.code,
    title: wire.title,
    domain: wire.domain ?? '—',
    technicalRequirements: wire.technical_requirements,
    interviewToken: wire.invite_token ?? '',
    openDate: formatDate(wire.opens_at ?? wire.created_at),
    closeDate: formatDate(wire.closes_at),
    clicks: wire.clicks,
    completed: wire.completed,
    live: wire.live,
  };
}

export function toDecision(value: string | null): InterviewDecision | null {
  return value ? (DECISION_LABELS[value] ?? null) : null;
}

export function toScoringStatus(value: 'evaluating' | 'done'): ScoringStatus {
  return value === 'done' ? 'Done' : 'Evaluating';
}

/** Ledger row in the shape the interviews table renders. */
export interface LedgerRow {
  id: string;
  code: string;
  candidateName: string;
  requisitionId: string;
  requisitionTitle: string;
  domain: string;
  scoringStatus: ScoringStatus;
  decision: InterviewDecision | null;
  concludedAt: string;
  durationSeconds: number;
  finalScore: number | null;
}

export function toLedgerRow(wire: ConsoleInterviewWire): LedgerRow {
  return {
    id: wire.id,
    code: wire.code ?? wire.id.slice(0, 8).toUpperCase(),
    candidateName: wire.candidate_name,
    requisitionId: wire.requisition_code,
    requisitionTitle: wire.requisition_title,
    domain: wire.domain ?? '—',
    scoringStatus: toScoringStatus(wire.scoring_status),
    decision: toDecision(wire.decision),
    concludedAt: wire.concluded_at ?? '',
    durationSeconds: wire.duration_seconds,
    finalScore: wire.final_score,
  };
}

export interface ReviewTrailEntry {
  at: string;
  actor: string;
  action: string;
  detail: string | null;
}

export interface ReviewData extends InterviewReview {
  code: string;
  reviewDecision: InterviewDecision | null;
  reviewTrail: ReviewTrailEntry[];
}

export function toReview(wire: ConsoleReviewWire): ReviewData {
  const transcript: TranscriptTurn[] = wire.transcript.map(t => ({
    id: t.id,
    at: formatClock(t.seconds),
    seconds: t.seconds,
    speaker: t.speaker === 'kandidly' ? 'AI' : 'Candidate',
    text: t.text,
  }));
  const rubric: RubricAssessment[] = wire.rubric.map(r => ({
    id: r.key,
    label: r.label,
    score: Math.round(r.score),
    weight: Math.round(r.weight),
    summary: r.summary,
    reasoning: r.reasoning,
  }));
  const proctorFrames: ProctorFrame[] = wire.proctor_frames.map(f => ({
    id: f.id,
    at: formatClock(f.seconds),
    seconds: f.seconds,
    signal: SIGNAL_LABELS[f.signal ?? 'clear'] ?? 'Clear',
    imageUrl: f.image_url ?? undefined,
  }));

  return {
    id: wire.id,
    code: wire.code ?? wire.id.slice(0, 8).toUpperCase(),
    candidateName: wire.candidate_name,
    requisitionId: wire.requisition_code,
    requisitionTitle: wire.requisition_title,
    domain: wire.domain ?? '—',
    scoringStatus: toScoringStatus(wire.scoring_status),
    concludedAt: wire.concluded_at ?? '',
    duration: formatDuration(wire.duration_seconds),
    audioSrc: wire.audio_url ?? '',
    finalScore: Math.round((wire.final_score ?? 0) * 10) / 10,
    percentile: wire.percentile ?? 0,
    recommendation: toDecision(wire.recommendation) ?? 'Hold',
    assessmentSummary:
      wire.assessment_summary ??
      'Scoring in progress — the assessment summary will appear once evaluation completes.',
    comparisonScores: wire.comparison_scores,
    transcript,
    proctorFrames,
    rubric,
    waveformPeaks: wire.waveform?.peaks ?? null,
    audioDurationSeconds: wire.waveform?.duration_seconds ?? null,
    reviewDecision: toDecision(wire.review_decision),
    reviewTrail: wire.review_trail.map(t => ({ ...t })),
  };
}

/* ── fetchers ─────────────────────────────────────────────────────────────── */

export const consoleApi = {
  getCatalog: async (): Promise<CatalogWire> =>
    (await api.get<CatalogWire>('/api/admin/console/catalog')).data,
  getRequisitions: async (): Promise<ConsoleRequisitionWire[]> =>
    (await api.get<ConsoleRequisitionWire[]>('/api/admin/console/requisitions')).data,
  getRequisition: async (id: string): Promise<ConsoleRequisitionDetailWire> =>
    (await api.get<ConsoleRequisitionDetailWire>(`/api/admin/console/requisitions/${id}`)).data,
  createRequisition: async (body: ConsoleRequisitionIn): Promise<ConsoleRequisitionDetailWire> =>
    (await api.post<ConsoleRequisitionDetailWire>('/api/admin/console/requisitions', body)).data,
  updateRequisition: async (id: string, body: ConsoleRequisitionIn): Promise<ConsoleRequisitionDetailWire> =>
    (await api.put<ConsoleRequisitionDetailWire>(`/api/admin/console/requisitions/${id}`, body)).data,
  setRequisitionStatus: async (id: string, status: string): Promise<void> => {
    await api.post(`/api/admin/requisitions/${id}/status`, { status });
  },
  getInterviews: async (): Promise<ConsoleInterviewWire[]> =>
    (await api.get<ConsoleInterviewWire[]>('/api/admin/console/interviews')).data,
  getReview: async (id: string): Promise<ConsoleReviewWire> =>
    (await api.get<ConsoleReviewWire>(`/api/admin/console/interviews/${id}`)).data,
  reviewInterview: async (id: string, decision: string, notes?: string): Promise<void> => {
    await api.post(`/api/admin/interviews/${id}/report/review`, { decision, notes });
  },
  getDashboard: async (): Promise<ConsoleDashboardWire> =>
    (await api.get<ConsoleDashboardWire>('/api/admin/console/dashboard')).data,
};

/* ── query hooks ──────────────────────────────────────────────────────────── */

export function useConsoleRequisitions() {
  return useQuery({
    queryKey: ['console', 'requisitions'],
    queryFn: consoleApi.getRequisitions,
    select: rows => rows.map(toRequisition),
  });
}

export function useConsoleRequisition(id: string | undefined) {
  return useQuery({
    queryKey: ['console', 'requisitions', id],
    queryFn: () => consoleApi.getRequisition(id!),
    enabled: !!id,
  });
}

export function useCatalog() {
  return useQuery({ queryKey: ['console', 'catalog'], queryFn: consoleApi.getCatalog });
}

export function useToggleRequisitionStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, live }: { id: string; live: boolean }) =>
      consoleApi.setRequisitionStatus(id, live ? 'open' : 'paused'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['console', 'requisitions'] }),
  });
}

export function useConsoleInterviews() {
  return useQuery({
    queryKey: ['console', 'interviews'],
    queryFn: consoleApi.getInterviews,
    select: rows => rows.map(toLedgerRow),
  });
}

export function useConsoleReview(id: string | undefined) {
  return useQuery({
    queryKey: ['console', 'interviews', id],
    queryFn: () => consoleApi.getReview(id!),
    enabled: !!id,
    select: toReview,
  });
}

export function useReviewDecision(interviewId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ decision, notes }: { decision: string; notes?: string }) =>
      consoleApi.reviewInterview(interviewId!, decision.toLowerCase(), notes),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['console', 'interviews'] });
    },
  });
}

export function useConsoleDashboard() {
  return useQuery({ queryKey: ['console', 'dashboard'], queryFn: consoleApi.getDashboard });
}
