/**
 * /i/:token — Invite landing page.
 * Resolves the link, shows errors for invalid states,
 * lets a dev pick a candidate account, claims the link, then routes by state.
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { ArrowRight, AlertCircle, Clock, XCircle, Lock, ChevronRight } from 'lucide-react';
import { publicApi, candidateApi } from '../../lib/api';
import { setAuth, clearAuth } from '../../lib/auth';
import { Button, Spinner } from '../../components/ui';
import type { DevUser, LinkResolveOut } from '../../lib/types';

// Map reason codes to friendly messages
function ErrorPanel({ reason }: { reason: string | null }) {
  // Reason codes come from backend resolve() in backend/app/domain/links.py:
  // {revoked, expired, maxed, requisition_closed, not_open_yet}. Unknown tokens
  // resolve as `expired`. `invalid` is a frontend-only fallback.
  const messages: Record<string, { icon: React.ReactNode; title: string; body: string }> = {
    revoked:             { icon: <XCircle size={20} />,     title: 'Link revoked',       body: 'This invite link has been revoked by the recruiter.' },
    expired:             { icon: <Clock size={20} />,       title: 'Link expired',       body: 'This invite link has passed its expiry date or is no longer valid.' },
    maxed:               { icon: <Lock size={20} />,        title: 'Link fully used',    body: 'This invite link has reached its maximum number of uses.' },
    requisition_closed:  { icon: <AlertCircle size={20} />, title: 'Position closed',    body: 'This position is no longer accepting applications.' },
    not_open_yet:        { icon: <Clock size={20} />,       title: 'Not open yet',       body: 'Applications for this role haven\'t opened yet.' },
    invalid:             { icon: <AlertCircle size={20} />, title: 'Invalid link',       body: 'This invite link doesn\'t exist or has been removed.' },
  };

  const info = messages[reason ?? 'invalid'] ?? messages['invalid'];

  return (
    <div
      className="w-full max-w-sm mx-auto rounded-xl border p-8 text-center space-y-3"
      style={{ borderColor: 'rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.05)' }}
    >
      <div
        className="size-12 rounded-xl flex items-center justify-center mx-auto"
        style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}
      >
        {info.icon}
      </div>
      <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{info.title}</h2>
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{info.body}</p>
    </div>
  );
}

// Dev user picker panel
function DevUserPicker({ onPick }: { onPick: (user: DevUser) => void }) {
  const { data: devUsers, isLoading } = useQuery({
    queryKey: ['dev-users'],
    queryFn: publicApi.getDevUsers,
  });

  const candidates = devUsers?.filter(u => u.role === 'candidate') ?? [];

  return (
    <div
      className="w-full rounded-xl border p-4 space-y-3"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
    >
      <p className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
        Dev mode — continue as
      </p>
      {isLoading ? (
        <div className="flex justify-center py-4"><Spinner size={18} /></div>
      ) : candidates.length === 0 ? (
        <p className="text-xs py-2 text-center" style={{ color: 'var(--text-muted)' }}>No candidate accounts found.</p>
      ) : (
        <div className="space-y-1">
          {candidates.map(u => (
            <button
              key={u.token}
              onClick={() => onPick(u)}
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 hover:bg-[var(--surface-hover)]"
              style={{ color: 'var(--text-primary)' }}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className="size-7 rounded-full flex items-center justify-center text-xs font-medium"
                  style={{ background: 'var(--surface-hover)', color: 'var(--text-secondary)' }}
                >
                  {u.email[0].toUpperCase()}
                </div>
                <span className="text-sm">{u.email}</span>
              </div>
              <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function routeByState(applicationId: string, state: string, navigate: ReturnType<typeof useNavigate>) {
  if (state === 'registered' || state === 'form_in_progress') {
    navigate(`/apply/${applicationId}/form`);
  } else if (
    state === 'form_submitted' ||
    state === 'plan_ready' ||
    state === 'in_lobby'
  ) {
    navigate(`/apply/${applicationId}/lobby`);
  } else if (state === 'in_interview') {
    navigate(`/apply/${applicationId}/lobby`); // rejoin
  } else {
    navigate(`/apply/${applicationId}/done`);
  }
}

export default function CandidateLanding() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [showPicker, setShowPicker] = useState(false);

  const { data: link, isLoading, error } = useQuery<LinkResolveOut>({
    queryKey: ['link', token],
    queryFn: () => publicApi.resolveLink(token!),
    enabled: !!token,
  });

  const claimMutation = useMutation({
    mutationFn: () => candidateApi.claim(token!),
    onSuccess: data => {
      routeByState(data.application_id, data.state, navigate);
    },
    onError: err => {
      const code = (err as { response?: { data?: { code?: string } } })?.response?.data?.code;
      if (code === 'forbidden') {
        // A non-candidate token (e.g. a recruiter/admin session left in
        // localStorage) can't claim — drop it and let them pick a candidate.
        clearAuth();
        setShowPicker(true);
      }
    },
  });

  // Extract a friendly message from a claim failure. The backend returns the
  // standard envelope { code, message } (backend/app/core/errors.py); a link
  // that lapsed between resolve and claim comes back as `link_invalid`.
  const claimErrorMessage = (): string => {
    const err = claimMutation.error as
      | { response?: { data?: { code?: string; message?: string } } }
      | undefined;
    const data = err?.response?.data;
    if (data?.code === 'link_invalid') {
      return data.message || 'This link is no longer valid. Please request a new one.';
    }
    if (data?.code === 'forbidden') {
      return 'That account can’t apply — choose a candidate account below to continue.';
    }
    return 'Something went wrong. Please try again.';
  };

  const handleStart = () => {
    // Dev flow: always show the account picker so a fresh run is one click away
    // (no localStorage clearing). Picking resets that candidate's prior app.
    setShowPicker(true);
  };

  const handlePickUser = async (user: DevUser) => {
    setAuth(user);
    setShowPicker(false);
    // Dev convenience: abandon any prior application for this link+candidate so
    // every pick starts a brand-new interview instead of resuming to "Thank you".
    try {
      await publicApi.devReset(token!, user.email);
    } catch {
      /* best-effort — proceed even if reset is unavailable */
    }
    claimMutation.mutate();
  };

  // ── Loading ──
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)' }}>
        <Spinner size={24} />
      </div>
    );
  }

  // ── Error fetching ──
  if (error || !link) {
    return (
      <CenteredLayout>
        <ErrorPanel reason="invalid" />
      </CenteredLayout>
    );
  }

  // ── Link not valid ──
  if (!link.status_ok) {
    return (
      <CenteredLayout>
        <ErrorPanel reason={link.reason} />
      </CenteredLayout>
    );
  }

  // ── Valid link ──
  return (
    <CenteredLayout>
      <div className="w-full max-w-sm mx-auto space-y-6">
        {/* Header */}
        <div className="text-center space-y-1">
          <p className="text-xs uppercase tracking-widest font-medium" style={{ color: 'var(--text-muted)' }}>
            You're invited to apply
          </p>
          <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            {link.title ?? 'Open Role'}
          </h1>
          {link.interview_type && (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              {link.interview_type} interview
            </p>
          )}
        </div>

        {/* What to expect */}
        <div
          className="rounded-xl border p-5 space-y-3"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <h2 className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>What to expect</h2>
          <ul className="space-y-2">
            {[
              'Fill in a short application form',
              'Complete a 30-minute AI voice interview',
              'We\'ll notify you with next steps',
            ].map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
                <span
                  className="size-5 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 mt-0.5"
                  style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
                >
                  {i + 1}
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Dev user picker */}
        {showPicker && (
          <DevUserPicker onPick={handlePickUser} />
        )}

        {/* CTA */}
        {!showPicker && (
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            loading={claimMutation.isPending}
            onClick={handleStart}
          >
            Start Application
            <ArrowRight size={16} />
          </Button>
        )}

        {claimMutation.isError && (
          <p className="text-xs text-center text-red-400">
            {claimErrorMessage()}
          </p>
        )}
      </div>
    </CenteredLayout>
  );
}

function CenteredLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: 'var(--background)' }}
    >
      <div className="w-full max-w-sm">
        {/* Logo mark */}
        <div className="flex justify-center mb-8">
          <div
            className="size-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            K
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
