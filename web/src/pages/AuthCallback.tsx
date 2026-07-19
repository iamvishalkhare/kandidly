/**
 * /auth/callback — lands here from the backend's WorkOS AuthKit callback.
 *
 * Success: `?next=<path>#token=<jwt>` — the JWT rides in the URL fragment
 * (never sent to any server, so no log/Referer leakage). We strip it from the
 * address bar immediately, fetch /api/auth/me to populate the auth store, and
 * continue to `next`.
 *
 * Failure: `#error=<code>` — for rejections of an authenticated account the
 * backend revokes the WorkOS session server-side first, so the next sign-in
 * prompts fresh. (`?error=<code>` is also read for robustness; it was the
 * carrier back when rejections bounced through WorkOS's logout URL.)
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight } from 'lucide-react';
import { authApi } from '../lib/api';
import { setAuth } from '../lib/auth';
import { Button, Spinner } from '../components/ui';

const ERROR_COPY: Record<string, { title: string; body: string }> = {
  auth_failed:           { title: 'Sign-in failed',        body: 'Something went wrong while signing you in. Please try again.' },
  state_mismatch:        { title: 'Sign-in expired',       body: 'This sign-in attempt expired or was already used. Please start again.' },
  not_allowlisted:       { title: 'Access is invite-only', body: 'Kandidly is currently invite-only and this email hasn’t been granted console access. If you were expecting access, contact the person who invited you.' },
  account_suspended:     { title: 'Account suspended',     body: 'Your account has been suspended. Contact your administrator or recruiter for help.' },
  account_invited:       { title: 'Invitation pending',    body: 'This account has a pending invitation. Use the invitation you received to activate it first.' },
  not_console_account:   { title: 'Not a console account', body: 'This email belongs to a candidate account, so it can’t open the console. If you received an interview link, open it directly.' },
  not_candidate_account: { title: 'Recruiter account',     body: 'This email belongs to a console (recruiter) account. Sign in with a different email to take the interview.' },
};

export default function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // StrictMode double-invoke guard
    ran.current = true;

    const hash = new URLSearchParams(window.location.hash.slice(1));
    const search = new URLSearchParams(window.location.search);
    const token = hash.get('token');
    const errCode = hash.get('error') ?? search.get('error');
    const nextRaw = search.get('next');
    const next = nextRaw && nextRaw.startsWith('/') && !nextRaw.startsWith('//') ? nextRaw : '/';

    // Get the token out of the address bar before anything else runs.
    window.history.replaceState(null, '', window.location.pathname);

    if (errCode || !token) {
      setError(errCode ?? 'auth_failed');
      return;
    }

    (async () => {
      try {
        const me = await authApi.me(token);
        setAuth({
          token,
          email: me.email,
          role: me.role,
          display_name: me.display_name,
          avatar_url: me.avatar_url,
          org_id: me.org_id,
        });
        navigate(next, { replace: true });
      } catch {
        setError('auth_failed');
      }
    })();
  }, [navigate]);

  if (!error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3" style={{ background: 'var(--background)' }}>
        <Spinner size={24} />
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Signing you in…</p>
      </div>
    );
  }

  const copy = ERROR_COPY[error] ?? ERROR_COPY.auth_failed;
  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ background: 'var(--background)' }}>
      <div
        className="w-full max-w-sm mx-auto rounded-xl border p-8 text-center space-y-4"
        style={{ borderColor: 'rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.05)' }}
      >
        <div
          className="size-12 rounded-xl flex items-center justify-center mx-auto"
          style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}
        >
          <AlertCircle size={20} />
        </div>
        <div className="space-y-2">
          <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{copy.title}</h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{copy.body}</p>
        </div>
        <Button variant="primary" className="w-full" onClick={() => navigate('/', { replace: true })}>
          Back to home
          <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  );
}
