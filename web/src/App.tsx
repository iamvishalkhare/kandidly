import { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import { cn } from './lib/utils';
import { getToken, getUser, subscribeAuth, setAuth } from './lib/auth';
import { authApi, publicApi } from './lib/api';
import { ToastProvider } from './components/ui';
import type { DevUser } from './lib/types';

// --- Pages ---
import Marketing         from './pages/Marketing';
import AuthCallback      from './pages/AuthCallback';
import CandidateLanding  from './pages/candidate/Landing';
import CandidateForm     from './pages/candidate/Form';
import CandidateLobby    from './pages/candidate/Lobby';
import CandidateDone     from './pages/candidate/Done';
// Lazy-loaded so the heavy livekit-client bundle only loads on the interview route.
const CandidateInterview = lazy(() => import('./pages/candidate/Interview'));
import ConsoleDashboard  from './pages/console/Dashboard';
import ConsoleInterviews from './pages/console/Interviews';
import ConsoleInvitations from './pages/console/Invitations';
import InterviewReview from './pages/console/InterviewReview';
import ConsoleRequisitions from './pages/console/Requisitions';
import RequisitionBuilder from './pages/console/RequisitionBuilder';
import NotFound          from './pages/NotFound';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

// ─── Auth hook ────────────────────────────────────────────────────────────────

function useAuth() {
  const [token, setToken] = useState(getToken);
  const [user, setUser]   = useState(getUser);

  useEffect(() => {
    // Re-read cached values whenever the auth store notifies.
    const unsubscribe = subscribeAuth(() => {
      setToken(getToken());
      setUser(getUser());
    });
    return unsubscribe;
  }, []);

  return { token, user, isLoggedIn: !!token };
}

// ─── Login screen ─────────────────────────────────────────────────────────────
// Real sign-in goes through WorkOS AuthKit (full-page redirect; the backend
// returns the app JWT on /auth/callback). Dev builds additionally list the
// seeded dev accounts (/api/public/dev-users — 404s outside dev).

const IS_DEV_BUILD = Boolean((import.meta as { env: Record<string, string | boolean> }).env.DEV);

function LoginScreen({ intent, returnTo, onPick }: {
  intent: 'console' | 'candidate';
  returnTo: string;
  onPick: (user: DevUser) => void;
}) {
  const { data: devUsers, isLoading, error } = useQuery({
    queryKey: ['dev-users'],
    queryFn: publicApi.getDevUsers,
    enabled: IS_DEV_BUILD,
    retry: false,
  });

  const roleColor = (role: string) => {
    if (role === 'admin' || role === 'recruiter') return 'text-primary-fixed-dim';
    if (role === 'candidate') return 'text-[var(--emerald-chip-text)]';
    return 'text-on-surface-variant';
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-surface-container-lowest">
      <div className="w-full max-w-sm border border-outline-variant">
        {/* Brand block */}
        <div className="p-5 border-b border-outline-variant bg-surface">
          <div className="flex items-center gap-2">
            <span className="size-2.5 bg-primary-container" />
            <h1 className="font-display text-lg font-bold tracking-tight text-primary-fixed-dim leading-none">KANDIDLY</h1>
          </div>
          <p className="label-mono text-text-muted mt-2 ml-[18px]">
            {intent === 'console' ? 'Voice console' : 'Candidate sign-in'}
          </p>
        </div>

        {/* Primary: WorkOS AuthKit hosted sign-in */}
        <div className="p-5 border-b border-outline-variant bg-surface-container-lowest">
          <a
            href={authApi.loginUrl(intent, returnTo)}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium bg-primary-container text-on-primary-container hover:opacity-90 transition-opacity"
          >
            Sign in
            <ChevronRight size={14} />
          </a>
          <p className="label-mono text-text-muted mt-3 text-center">
            Google · email &amp; password · magic link
          </p>
        </div>

        {!IS_DEV_BUILD ? null : (
        <div className="bg-surface-container-lowest">
          <p className="label-mono text-text-muted px-4 pt-4 pb-1">Dev access — seeded accounts</p>
          {isLoading && (
            <div className="py-8 flex flex-col items-center gap-2 text-text-muted">
              <svg className="animate-spin size-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="label-mono">Loading accounts…</p>
            </div>
          )}
          {error && (
            <div className="py-8 text-center">
              <p className="label-mono text-error">ERR_BACKEND_UNREACHABLE</p>
              <p className="text-xs mt-1 text-text-muted">Could not load dev accounts. Is the backend running?</p>
            </div>
          )}
          {devUsers && devUsers.length === 0 && (
            <p className="py-8 text-center label-mono text-text-muted">No dev users found</p>
          )}
          {devUsers?.map((u) => (
            <button
              key={u.token}
              onClick={() => onPick(u)}
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-sm border-b border-outline-variant last:border-b-0 text-text-primary hover:bg-surface-container transition-colors duration-150"
            >
              <div className="flex items-center gap-3">
                <div className="size-8 flex items-center justify-center border border-outline-variant bg-surface font-display font-bold text-primary-fixed-dim">
                  {u.email[0].toUpperCase()}
                </div>
                <div className="text-left">
                  <p className="text-sm font-medium text-text-primary">{u.email}</p>
                  <p className={cn('label-mono', roleColor(u.role))}>{u.role}</p>
                </div>
              </div>
              <ChevronRight size={14} className="text-text-muted" />
            </button>
          ))}
        </div>
        )}
      </div>
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────

function AppInner() {
  const { isLoggedIn } = useAuth();
  // If not logged in and hitting a console or /apply route, show login screen.
  // Must come from the router (not window.location) so client-side <Link>
  // navigations re-evaluate the gate.
  const location = useLocation();
  const path = location.pathname;
  const needsAuth = path.startsWith('/apply') || path.startsWith('/console');

  const handlePick = (picked: DevUser) => {
    setAuth(picked);
    // Navigate to console if admin/recruiter, otherwise refresh
    window.location.pathname = (picked.role === 'admin' || picked.role === 'recruiter') ? '/console' : path;
  };

  if (!isLoggedIn && needsAuth) {
    return (
      <LoginScreen
        intent={path.startsWith('/console') ? 'console' : 'candidate'}
        returnTo={path + location.search}
        onPick={handlePick}
      />
    );
  }

  return (
    <Suspense fallback={<div className="min-h-screen" style={{ background: 'var(--background)' }} />}>
    <Routes>
      {/* Marketing (public-facing) */}
      <Route path="/" element={<Marketing />} />

      {/* WorkOS AuthKit return leg (token/error arrives in the URL fragment) */}
      <Route path="/auth/callback" element={<AuthCallback />} />

      {/* Console (standalone pages with their own layout) */}
      <Route path="/console" element={<ConsoleDashboard />} />
      <Route path="/console/interviews" element={<ConsoleInterviews />} />
      <Route path="/console/interviews/:interviewId" element={<InterviewReview />} />
      <Route path="/console/invitations" element={<ConsoleInvitations />} />
      <Route path="/console/requisitions" element={<ConsoleRequisitions />} />
      <Route path="/console/requisitions/new" element={<RequisitionBuilder />} />
      <Route path="/console/requisitions/:requisitionId" element={<RequisitionBuilder />} />

      {/* Candidate (public-facing) */}
      <Route path="/i/:token"                   element={<CandidateLanding />} />
      <Route path="/apply/:applicationId/form"      element={<CandidateForm />} />
      <Route path="/apply/:applicationId/lobby"     element={<CandidateLobby />} />
      <Route path="/apply/:applicationId/interview" element={<CandidateInterview />} />
      <Route path="/apply/:applicationId/done"      element={<CandidateDone />} />

      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AppInner />
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
