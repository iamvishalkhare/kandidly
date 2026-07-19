/**
 * Console API client: typed wrappers over /api/admin/console plus mappers
 * from the backend's snake_case wire shapes into the UI-facing interfaces
 * the console pages already render (Requisition, InterviewRecord, …).
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type { AccountOut, UsageOut } from './types';
import type { Requisition } from '../pages/console/requisitionData';
import type {
  IntegrityBand,
  IntegritySummary,
  IntegrityVerdict,
  InterviewDecision,
  InterviewReview,
  ProctorFrame,
  RubricAssessment,
  ScoringStatus,
  ScreeningAnswer,
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
  invite_only: boolean;
  clicks: number;
  completed: number;
}

export interface ConsoleRequisitionDetailWire extends ConsoleRequisitionWire {
  objective: string | null;
  tone: string;
  end_date: string | null;
  proctoring_enabled: boolean;
  duration_minutes: number;
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
  end_date: string | null;
  proctoring_enabled: boolean;
  /** Invite-only access: only guest-listed emails can claim the (same) interview URL. */
  invite_only: boolean;
  /** Interview length in minutes (15–90; the agent ends the interview at this cap). */
  duration_minutes: number;
  sample_questions: BuilderQuestionWire[];
  screening_fields: BuilderFieldWire[];
  rubric: BuilderCriterionWire[];
  deploy: boolean;
}

/* ── invite-only guest list ───────────────────────────────────────────────── */

export interface InviteWire {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  email_status: 'queued' | 'sent' | 'failed';
  last_emailed_at: string | null;
  created_at: string;
  status: 'invited' | 'claimed' | 'completed';
}

export interface InvitesMutationWire {
  added: number;
  duplicates: number;
  invalid: { row: number; reason: string }[];
}

export interface InviteIn {
  email: string;
  first_name: string;
  last_name: string;
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
  candidate_email: string | null;
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
  selfie_url: string | null;
  transcript: { id: string; seconds: number; speaker: string; text: string }[];
  screening_answers: {
    key: string;
    label: string;
    field_type: string;
    required: boolean;
    answered: boolean;
    answer: string | null;
    file_url: string | null;
    file_mime: string | null;
    file_name: string | null;
  }[];
  rubric: { key: string; label: string; weight: number; score: number; summary: string; reasoning: string }[];
  integrity: {
    verdict: IntegrityVerdict;
    proctoring_enabled: boolean;
    frame_count: number;
    analyzed_count: number;
    signal_counts: Record<string, number>;
    event_counts: Record<string, number>;
    identity_verdict: string | null;
    score: number | null;
    band: IntegrityBand | null;
    summary: string | null;
  } | null;
  review_trail: { at: string; actor: string; action: string; detail: string | null }[];
}

export interface ProctorFrameWire {
  id: string;
  seconds: number;
  signal: string | null;
  image_url: string | null;
  analyzed: boolean;
  note: string | null;
}

export interface ProctorFramePageWire {
  items: ProctorFrameWire[];
  total: number;
  offset: number;
  limit: number;
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
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
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
    status: wire.status,
    inviteOnly: wire.invite_only,
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
  candidateEmail: string | null;
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
    candidateEmail: wire.candidate_email,
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

export function toProctorFrame(f: ProctorFrameWire): ProctorFrame {
  return {
    id: f.id,
    at: formatClock(f.seconds),
    seconds: f.seconds,
    // Unanalyzed frames read "Pending", never a false "Clear".
    signal: f.analyzed ? (SIGNAL_LABELS[f.signal ?? 'clear'] ?? 'Clear') : 'Pending',
    imageUrl: f.image_url ?? undefined,
    analyzed: f.analyzed,
    note: f.note,
  };
}

export function toReview(wire: ConsoleReviewWire): ReviewData {
  const transcript: TranscriptTurn[] = wire.transcript.map(t => ({
    id: t.id,
    at: formatClock(t.seconds),
    seconds: t.seconds,
    speaker: t.speaker === 'kandidly' ? 'AI' : 'Candidate',
    text: t.text,
  }));
  const screeningAnswers: ScreeningAnswer[] = (wire.screening_answers ?? []).map(answer => ({
    key: answer.key,
    label: answer.label,
    fieldType: answer.field_type,
    required: answer.required,
    answered: answer.answered,
    answer: answer.answer,
    fileUrl: answer.file_url,
    fileMime: answer.file_mime,
    fileName: answer.file_name,
  }));
  const rubric: RubricAssessment[] = wire.rubric.map(r => ({
    id: r.key,
    label: r.label,
    score: Math.round(r.score),
    weight: Math.round(r.weight),
    summary: r.summary,
    reasoning: r.reasoning,
  }));
  const integrity: IntegritySummary | null = wire.integrity
    ? {
        verdict: wire.integrity.verdict,
        proctoringEnabled: wire.integrity.proctoring_enabled,
        frameCount: wire.integrity.frame_count,
        analyzedCount: wire.integrity.analyzed_count,
        signalCounts: wire.integrity.signal_counts,
        eventCounts: wire.integrity.event_counts,
        identityVerdict: wire.integrity.identity_verdict,
        score: wire.integrity.score,
        band: wire.integrity.band,
        summary: wire.integrity.summary,
      }
    : null;

  return {
    id: wire.id,
    code: wire.code ?? wire.id.slice(0, 8).toUpperCase(),
    candidateName: wire.candidate_name,
    candidateEmail: wire.candidate_email,
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
    screeningAnswers,
    integrity,
    rubric,
    waveformPeaks: wire.waveform?.peaks ?? null,
    audioDurationSeconds: wire.waveform?.duration_seconds ?? null,
    selfieUrl: wire.selfie_url,
    reviewDecision: toDecision(wire.review_decision),
    reviewTrail: wire.review_trail.map(t => ({ ...t })),
  };
}

/* ── fetchers ─────────────────────────────────────────────────────────────── */

export const consoleApi = {
  getMe: async (): Promise<AccountOut> =>
    (await api.get<AccountOut>('/api/admin/console/me')).data,
  getUsage: async (): Promise<UsageOut> =>
    (await api.get<UsageOut>('/api/admin/console/usage')).data,
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
  /** Soft delete: requisition disappears from the console; its interviews stay. */
  deleteRequisition: async (id: string): Promise<void> => {
    await api.delete(`/api/admin/console/requisitions/${id}`);
  },
  setRequisitionStatus: async (id: string, status: string): Promise<void> => {
    await api.post(`/api/admin/requisitions/${id}/status`, { status });
  },
  getInterviews: async (): Promise<ConsoleInterviewWire[]> =>
    (await api.get<ConsoleInterviewWire[]>('/api/admin/console/interviews')).data,
  /** Hard delete: DB rows + S3 objects + Redis cache. 403s for every account
   * except the one this is currently gated to (backend/app/api/console.py). */
  deleteInterview: async (id: string): Promise<void> => {
    await api.delete(`/api/admin/console/interviews/${id}`);
  },
  getReview: async (id: string): Promise<ConsoleReviewWire> =>
    (await api.get<ConsoleReviewWire>(`/api/admin/console/interviews/${id}`)).data,
  getSnapshots: async (id: string, offset: number, limit: number): Promise<ProctorFramePageWire> =>
    (
      await api.get<ProctorFramePageWire>(
        `/api/admin/console/interviews/${id}/snapshots?offset=${offset}&limit=${limit}`,
      )
    ).data,
  reviewInterview: async (id: string, decision: string, notes?: string): Promise<void> => {
    await api.post(`/api/admin/interviews/${id}/report/review`, { decision, notes });
  },
  getDashboard: async (): Promise<ConsoleDashboardWire> =>
    (await api.get<ConsoleDashboardWire>('/api/admin/console/dashboard')).data,
  /* invite-only guest list */
  getInvites: async (reqId: string): Promise<InviteWire[]> =>
    (await api.get<InviteWire[]>(`/api/admin/console/requisitions/${reqId}/invites`)).data,
  addInvites: async (reqId: string, invites: InviteIn[]): Promise<InvitesMutationWire> =>
    (
      await api.post<InvitesMutationWire>(`/api/admin/console/requisitions/${reqId}/invites`, {
        invites,
      })
    ).data,
  importInvites: async (reqId: string, file: File): Promise<InvitesMutationWire> => {
    const form = new FormData();
    form.append('file', file);
    return (
      await api.post<InvitesMutationWire>(
        `/api/admin/console/requisitions/${reqId}/invites/import`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
    ).data;
  },
  revokeInvite: async (reqId: string, inviteId: string): Promise<void> => {
    await api.delete(`/api/admin/console/requisitions/${reqId}/invites/${inviteId}`);
  },
  resendInvite: async (reqId: string, inviteId: string): Promise<void> => {
    await api.post(`/api/admin/console/requisitions/${reqId}/invites/${inviteId}/resend`);
  },
};

/* ── query hooks ──────────────────────────────────────────────────────────── */

export function useConsoleMe() {
  return useQuery({ queryKey: ['console', 'me'], queryFn: consoleApi.getMe });
}

export function useConsoleUsage() {
  return useQuery({ queryKey: ['console', 'usage'], queryFn: consoleApi.getUsage });
}

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
    // Keep the Evaluating chips honest while any scoring run is in flight.
    // NB: the callback receives the raw wire rows, not the `select`-mapped ones.
    refetchInterval: query =>
      query.state.data?.some(row => row.scoring_status === 'evaluating') ? 10_000 : false,
  });
}

/** Vision/verdict pipeline still running: frames exist, analysis has started
 * (so a provider is configured), and the final LLM score hasn't landed. */
function integrityBusy(wire: ConsoleReviewWire): boolean {
  const i = wire.integrity;
  return !!i && i.frame_count > 0 && i.analyzed_count > 0 && i.score == null;
}

export function useConsoleReview(id: string | undefined) {
  return useQuery({
    queryKey: ['console', 'interviews', id],
    queryFn: () => consoleApi.getReview(id!),
    enabled: !!id,
    select: toReview,
    // Poll while evaluation is in flight so the page flips to Done on its own,
    // then more slowly while frame analysis / the integrity verdict finish.
    // NB: the callback receives the raw wire shape, not the `select`-mapped one.
    refetchInterval: query => {
      const wire = query.state.data;
      if (!wire) return false;
      if (wire.scoring_status === 'evaluating') return 4_000;
      return integrityBusy(wire) ? 10_000 : false;
    },
  });
}

const FRAME_PAGE_SIZE = 10;

/** Paginated proctor filmstrip; `poll` keeps fetched pages fresh while the
 * vision pipeline is still analyzing frames. */
export function useProctorFrames(id: string | undefined, poll: boolean) {
  return useInfiniteQuery({
    queryKey: ['console', 'interviews', id, 'snapshots'],
    queryFn: ({ pageParam }) => consoleApi.getSnapshots(id!, pageParam, FRAME_PAGE_SIZE),
    initialPageParam: 0,
    getNextPageParam: last => {
      const next = last.offset + last.items.length;
      return next < last.total ? next : undefined;
    },
    enabled: !!id,
    refetchInterval: poll ? 10_000 : false,
    select: data => ({
      frames: data.pages.flatMap(page => page.items.map(toProctorFrame)),
      total: data.pages[0]?.total ?? 0,
    }),
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

/** Guest list for an invite-only requisition. Polls lightly while any invite
 * email is still queued so delivery states settle on their own. */
export function useInvites(reqId: string | undefined) {
  return useQuery({
    queryKey: ['console', 'requisitions', reqId, 'invites'],
    queryFn: () => consoleApi.getInvites(reqId!),
    enabled: !!reqId,
    refetchInterval: query =>
      query.state.data?.some(i => i.email_status === 'queued') ? 8_000 : false,
  });
}

export function useInviteMutations(reqId: string | undefined) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['console', 'requisitions', reqId, 'invites'] });
  const add = useMutation({
    mutationFn: (invites: InviteIn[]) => consoleApi.addInvites(reqId!, invites),
    onSettled: invalidate,
  });
  const importFile = useMutation({
    mutationFn: (file: File) => consoleApi.importInvites(reqId!, file),
    onSettled: invalidate,
  });
  const revoke = useMutation({
    mutationFn: (inviteId: string) => consoleApi.revokeInvite(reqId!, inviteId),
    onSettled: invalidate,
  });
  const resend = useMutation({
    mutationFn: (inviteId: string) => consoleApi.resendInvite(reqId!, inviteId),
    onSettled: invalidate,
  });
  return { add, importFile, revoke, resend };
}

export function useDeleteInterview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => consoleApi.deleteInterview(id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['console', 'interviews'] });
      queryClient.invalidateQueries({ queryKey: ['console', 'dashboard'] });
    },
  });
}
