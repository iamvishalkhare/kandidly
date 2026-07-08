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

const API_BASE = (import.meta as { env: Record<string, string> }).env.VITE_API_BASE || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
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
  resolveLink: async (token: string): Promise<LinkResolveOut> => {
    const { data } = await api.get<LinkResolveOut>(`/api/public/i/${token}`);
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

// ─── Candidate ─────────────────────────────────────────────────────────────────

export const candidateApi = {
  claim: async (token: string): Promise<ClaimOut> => {
    const { data } = await api.post<ClaimOut>(`/api/candidate/i/${token}/claim`);
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
    const { data } = await api.post<JoinOut>(`/api/candidate/applications/${id}/join`);
    return data;
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
