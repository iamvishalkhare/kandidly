/**
 * Axios client with bearer-token interceptor.
 * Typed wrapper functions for every backend route.
 */

import axios from 'axios';
import { getToken, clearAuth } from './auth';
import type {
  ApplicationOut,
  AdminApplicationDetailOut,
  AdminApplicationListOut,
  ClaimOut,
  ConfigOut,
  ConsentIn,
  DevUser,
  FormPatchIn,
  FormSubmitOut,
  FormTemplateOut,
  FunnelOut,
  JoinOut,
  LinkOut,
  LinkResolveOut,
  ReportOut,
  RequisitionOut,
  RubricOut,
  TranscriptOut,
} from './types';

// Dev pages served from a non-localhost host (LAN IP, HTTPS tunnel for phone
// testing) can't reach the laptop's localhost:8000, so they call the API
// same-origin and let the Vite dev proxy forward /api (see vite.config.ts).
// Production builds always use the configured absolute base.
const env = (import.meta as { env: Record<string, string | boolean> }).env;
const API_BASE =
  env.DEV && !['localhost', '127.0.0.1'].includes(window.location.hostname)
    ? ''
    : (env.VITE_API_BASE as string) || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  // Sends the console gate cookie (set by Caddy basicauth in prod — see
  // infra/Caddyfile.prod) on the cross-origin app→api requests. No-op in dev.
  withCredentials: true,
});

// Attach token on every request
api.interceptors.request.use(cfg => {
  const token = getToken();
  if (token && cfg.headers) {
    cfg.headers['Authorization'] = `Bearer ${token}`;
  }
  return cfg;
});

// On 401: clear auth so the UI can prompt re-login.
// Guard with a flag so concurrent 401s don't call clearAuth() multiple times.
let _clearing = false;
api.interceptors.response.use(
  res => res,
  err => {
    if (err?.response?.status === 401 && !_clearing) {
      _clearing = true;
      clearAuth();
      // Reset flag on next microtask so future 401s (after re-login) still work.
      Promise.resolve().then(() => { _clearing = false; });
    }
    return Promise.reject(err);
  }
);

// Legacy helper kept for App.tsx compatibility
export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common['Authorization'];
  }
}

// ─── Public ────────────────────────────────────────────────────────────────────

export const publicApi = {
  getConfig: async (): Promise<ConfigOut> => {
    const { data } = await api.get<ConfigOut>('/api/public/config');
    return data;
  },
  resolveLink: async (token: string, captchaToken?: string | null): Promise<LinkResolveOut> => {
    const { data } = await api.get<LinkResolveOut>(
      `/api/public/i/${token}`,
      captchaToken ? { headers: { 'X-Recaptcha-Token': captchaToken } } : undefined,
    );
    return data;
  },
  getDevUsers: async (): Promise<DevUser[]> => {
    const { data } = await api.get<DevUser[]>('/api/public/dev-users');
    return data;
  },
  // Dev-only: abandon a candidate's current application for this link so the
  // next claim starts a fresh interview run.
  devReset: async (token: string, email: string): Promise<{ reset: number }> => {
    const { data } = await api.post<{ reset: number }>('/api/public/dev-reset', { token, email });
    return data;
  },
};

// ─── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  /** Revokes the current bearer token server-side (Redis denylist + audit). */
  logout: async (): Promise<void> => {
    await api.post('/api/auth/logout');
  },
};

// ─── Candidate ─────────────────────────────────────────────────────────────────

export const candidateApi = {
  claim: async (token: string, captchaToken?: string | null): Promise<ClaimOut> => {
    const { data } = await api.post<ClaimOut>(
      `/api/candidate/i/${token}/claim`,
      undefined,
      captchaToken ? { headers: { 'X-Recaptcha-Token': captchaToken } } : undefined,
    );
    return data;
  },
  getApplication: async (id: string): Promise<ApplicationOut> => {
    const { data } = await api.get<ApplicationOut>(`/api/candidate/applications/${id}`);
    return data;
  },
  patchForm: async (id: string, answers_partial: Record<string, unknown>): Promise<void> => {
    const body: FormPatchIn = { answers_partial };
    await api.patch(`/api/candidate/applications/${id}/form`, body);
  },
  uploadResume: async (id: string, file: File): Promise<{ file_id: string; parse_status: string }> => {
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await api.post(`/api/candidate/applications/${id}/resume`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
  submitForm: async (id: string, captchaToken?: string | null): Promise<FormSubmitOut> => {
    const { data } = await api.post<FormSubmitOut>(
      `/api/candidate/applications/${id}/form/submit`,
      undefined,
      captchaToken ? { headers: { 'X-Recaptcha-Token': captchaToken } } : undefined,
    );
    return data;
  },
  postConsent: async (id: string, body: ConsentIn): Promise<void> => {
    await api.post(`/api/candidate/applications/${id}/consent`, body);
  },
  postSelfie: async (id: string, blob: Blob): Promise<{ file_id: string }> => {
    const fd = new FormData();
    fd.append('image', blob, 'selfie.webp');
    const { data } = await api.post(`/api/candidate/applications/${id}/selfie`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
  join: async (id: string): Promise<JoinOut> => {
    // 202 = "not ready yet" (agent/plan still provisioning). axios treats 2xx as
    // success, so reject 202 explicitly → the caller's catch polls with retry_after_s
    // instead of connecting with an empty token.
    const { data } = await api.post<JoinOut>(`/api/candidate/applications/${id}/join`, undefined, {
      validateStatus: s => s >= 200 && s < 300 && s !== 202,
    });
    return data;
  },

  // Interview recording (browser MediaRecorder chunks; docs/ARTIFACTS.md)
  uploadRecordingChunk: async (interviewId: string, seq: number, blob: Blob): Promise<void> => {
    const fd = new FormData();
    fd.append('chunk', blob, `chunk-${seq}`);
    fd.append('seq', String(seq));
    await api.post(`/api/candidate/interviews/${interviewId}/recording/chunks`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  completeRecording: async (
    interviewId: string,
    body: { chunks: number; started_at: string; mime: string },
  ): Promise<void> => {
    await api.post(`/api/candidate/interviews/${interviewId}/recording/complete`, body);
  },

  // Proctoring ingest during the live interview
  uploadSnapshot: async (interviewId: string, blob: Blob, capturedAt: string): Promise<void> => {
    const fd = new FormData();
    fd.append('image', blob, 'frame.webp');
    fd.append('captured_at', capturedAt);
    await api.post(`/api/candidate/interviews/${interviewId}/snapshots`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  postProctorEvents: async (
    interviewId: string,
    events: Array<{ type: string; client_ts: string; payload?: Record<string, unknown> }>,
  ): Promise<void> => {
    await api.post(`/api/candidate/interviews/${interviewId}/proctor-events`, { events });
  },
};

// ─── Admin ─────────────────────────────────────────────────────────────────────

export const adminApi = {
  // Funnel
  getFunnel: async (): Promise<FunnelOut> => {
    const { data } = await api.get<FunnelOut>('/api/admin/funnel');
    return data;
  },

  // Requisitions
  getRequisitions: async (): Promise<RequisitionOut[]> => {
    const { data } = await api.get<RequisitionOut[]>('/api/admin/requisitions');
    return data;
  },
  getRequisition: async (id: string): Promise<RequisitionOut> => {
    const { data } = await api.get<RequisitionOut>(`/api/admin/requisitions/${id}`);
    return data;
  },
  createRequisition: async (body: {
    title: string;
    interview_type: string;
    form_template_id: string;
    rubric_id: string;
  }): Promise<RequisitionOut> => {
    const { data } = await api.post<RequisitionOut>('/api/admin/requisitions', body);
    return data;
  },
  setRequisitionStatus: async (id: string, status: string): Promise<RequisitionOut> => {
    const { data } = await api.post<RequisitionOut>(`/api/admin/requisitions/${id}/status`, { status });
    return data;
  },
  createLink: async (reqId: string, kind: 'open' | 'personal', email?: string): Promise<LinkOut> => {
    const { data } = await api.post<LinkOut>(`/api/admin/requisitions/${reqId}/links`, { kind, email });
    return data;
  },
  revokeLink: async (linkId: string): Promise<LinkOut> => {
    const { data } = await api.post<LinkOut>(`/api/admin/links/${linkId}/revoke`);
    return data;
  },

  // Applications
  getApplications: async (reqId: string): Promise<AdminApplicationListOut[]> => {
    const { data } = await api.get<AdminApplicationListOut[]>(`/api/admin/requisitions/${reqId}/applications`);
    return data;
  },
  getApplication: async (id: string): Promise<AdminApplicationDetailOut> => {
    const { data } = await api.get<AdminApplicationDetailOut>(`/api/admin/applications/${id}`);
    return data;
  },

  // Transcript & Report
  getTranscript: async (interviewId: string): Promise<TranscriptOut> => {
    const { data } = await api.get<TranscriptOut>(`/api/admin/interviews/${interviewId}/transcript`);
    return data;
  },
  getReport: async (interviewId: string): Promise<ReportOut> => {
    const { data } = await api.get<ReportOut>(`/api/admin/interviews/${interviewId}/report`);
    return data;
  },
  reviewReport: async (interviewId: string, decision: string, notes?: string): Promise<void> => {
    await api.post(`/api/admin/interviews/${interviewId}/report/review`, { decision, notes });
  },

  // Templates & Rubrics
  getFormTemplates: async (): Promise<FormTemplateOut[]> => {
    const { data } = await api.get<FormTemplateOut[]>('/api/admin/form-templates');
    return data;
  },
  publishTemplate: async (id: string): Promise<FormTemplateOut> => {
    const { data } = await api.post<FormTemplateOut>(`/api/admin/form-templates/${id}/publish`);
    return data;
  },
  getRubrics: async (): Promise<RubricOut[]> => {
    const { data } = await api.get<RubricOut[]>('/api/admin/rubrics');
    return data;
  },
  publishRubric: async (id: string): Promise<RubricOut> => {
    const { data } = await api.post<RubricOut>(`/api/admin/rubrics/${id}/publish`);
    return data;
  },

  // Phase-1 text-chat interview harness (SPEC §18.5)
  chatStart: async (interviewId: string): Promise<ChatTurnOut> => {
    const { data } = await api.post<ChatTurnOut>(`/api/admin/interviews/${interviewId}/chat/start`);
    return data;
  },
  chatReply: async (interviewId: string, text: string): Promise<ChatTurnOut> => {
    const { data } = await api.post<ChatTurnOut>(`/api/admin/interviews/${interviewId}/chat/reply`, { text });
    return data;
  },
};

/** Response of chat/start and chat/reply — the harness's kandidly turn. */
export interface ChatTurnOut {
  resumed?: boolean;
  turn?: { seq: number; speaker: string; text: string; decision: string };
  node?: { id: string; title: string; state: string };
  overrides?: string[];
  ended?: boolean;
}
