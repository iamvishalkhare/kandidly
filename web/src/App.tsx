import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Outlet, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Briefcase,
  FileText,
  BookOpen,
  LogOut,
  ChevronRight,
  Plus,
} from 'lucide-react';
import { cn } from './lib/utils';
import { getToken, getUser, clearAuth, subscribeAuth, setAuth } from './lib/auth';
import { publicApi } from './lib/api';
import { ToastProvider } from './components/ui';
import type { DevUser } from './lib/types';

// --- Pages ---
import Marketing         from './pages/Marketing';
import CandidateLanding  from './pages/candidate/Landing';
import CandidateForm     from './pages/candidate/Form';
import CandidateLobby    from './pages/candidate/Lobby';
import CandidateDone     from './pages/candidate/Done';
import AdminDashboard    from './pages/admin/Dashboard';
import ConsoleDashboard  from './pages/console/Dashboard';
import ConsoleRequisitions from './pages/console/Requisitions';
import RequisitionBuilder from './pages/console/RequisitionBuilder';
import RequisitionsList  from './pages/admin/RequisitionsList';
import RequisitionDetail from './pages/admin/RequisitionDetail';
import ApplicationDetail from './pages/admin/ApplicationDetail';
import FormsPage         from './pages/admin/Forms';
import RubricsPage       from './pages/admin/Rubrics';
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

// ─── Dev login screen ─────────────────────────────────────────────────────────

function LoginScreen({ onPick }: { onPick: (user: DevUser) => void }) {
  const { data: devUsers, isLoading, error } = useQuery({
    queryKey: ['dev-users'],
    queryFn: publicApi.getDevUsers,
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
          <p className="label-mono text-text-muted mt-2 ml-[18px]">Voice console // dev access</p>
        </div>

        <div className="bg-surface-container-lowest">
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

        <p className="label-mono text-center text-text-muted border-t border-outline-variant px-4 py-3 bg-surface">
          Tokens auto-generated from seed data
        </p>
      </div>
    </div>
  );
}

// ─── Admin Layout ─────────────────────────────────────────────────────────────

function AdminLayout() {
  const location = useLocation();
  const { user } = useAuth();

  const navItems = [
    { name: 'Dashboard',     path: '/admin',               icon: LayoutDashboard, exact: true },
    { name: 'Requisitions',  path: '/admin/requisitions',  icon: Briefcase },
    { name: 'Form Templates',path: '/admin/forms',         icon: FileText },
    { name: 'Rubrics',       path: '/admin/rubrics',       icon: BookOpen },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-surface-container-lowest">
      {/* Sidebar — Brutalist Blueprint shell */}
      <aside className="w-64 flex flex-col shrink-0 border-r border-outline-variant bg-surface-container-lowest">
        {/* Brand block */}
        <Link to="/admin" className="h-16 px-5 flex flex-col justify-center border-b border-outline-variant shrink-0">
          <span className="flex items-center gap-2">
            <span className="size-2.5 bg-primary-container" />
            <span className="font-display text-lg font-bold tracking-tight text-primary-fixed-dim leading-none">KANDIDLY</span>
          </span>
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.25em] text-text-muted mt-1 ml-[18px]">Voice console</span>
        </Link>

        {/* Primary CTA */}
        <div className="p-4 border-b border-outline-variant shrink-0">
          <Link
            to="/admin/requisitions"
            className="flex items-center justify-center gap-2 w-full py-2.5 bg-primary-container text-on-primary-container label-mono font-bold border border-primary-container hover:bg-transparent hover:text-primary-fixed-dim transition-colors duration-150"
          >
            <Plus size={14} />
            New requisition
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto">
          {navItems.map(item => {
            const isActive = item.exact
              ? location.pathname === item.path
              : location.pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 px-5 py-3.5 label-mono transition-colors duration-150',
                  isActive
                    ? 'bg-primary-container text-on-primary-container font-bold'
                    : 'text-text-secondary hover:bg-surface-container hover:text-text-primary'
                )}
              >
                <item.icon size={16} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="p-4 border-t border-outline-variant shrink-0">
          <div className="flex items-center gap-3">
            <div className="size-9 flex items-center justify-center border border-outline-variant bg-surface font-display font-bold text-primary-fixed-dim shrink-0">
              {user?.email?.[0]?.toUpperCase() ?? 'A'}
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="text-xs font-medium truncate text-text-primary">{user?.email ?? 'Admin'}</p>
              <p className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-text-muted">{user?.role ?? 'admin'}</p>
            </div>
            <button
              onClick={clearAuth}
              className="p-1.5 border border-transparent text-text-muted hover:border-outline-variant hover:text-text-primary transition-colors duration-150"
              title="Sign out"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto bg-surface-container-lowest">
        <div className="max-w-[1600px] mx-auto px-6 py-6 md:px-8 md:py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────

function AppInner() {
  const { isLoggedIn } = useAuth();
  // If not logged in and hitting an admin or /apply route, show login screen
  const path = window.location.pathname;
  const needsAuth = path.startsWith('/admin') || path.startsWith('/apply') || path.startsWith('/console');

  const handlePick = (picked: DevUser) => {
    setAuth(picked);
    // Navigate to admin if admin/recruiter, otherwise refresh
    window.location.pathname = (picked.role === 'admin' || picked.role === 'recruiter') ? '/admin' : path;
  };

  if (!isLoggedIn && needsAuth) {
    return (
      <LoginScreen onPick={handlePick} />
    );
  }

  return (
    <Routes>
      {/* Marketing (public-facing) */}
      <Route path="/" element={<Marketing />} />

      {/* Console (standalone pages with their own layout) */}
      <Route path="/console" element={<ConsoleDashboard />} />
      <Route path="/console/requisitions" element={<ConsoleRequisitions />} />
      <Route path="/console/requisitions/new" element={<RequisitionBuilder />} />

      {/* Candidate (public-facing) */}
      <Route path="/i/:token"                   element={<CandidateLanding />} />
      <Route path="/apply/:applicationId/form"  element={<CandidateForm />} />
      <Route path="/apply/:applicationId/lobby" element={<CandidateLobby />} />
      <Route path="/apply/:applicationId/done"  element={<CandidateDone />} />

      {/* Admin */}
      <Route path="/admin" element={<AdminLayout />}>
        <Route index                            element={<AdminDashboard />} />
        <Route path="requisitions"              element={<RequisitionsList />} />
        <Route path="requisitions/:id"          element={<RequisitionDetail />} />
        <Route path="applications/:id"          element={<ApplicationDetail />} />
        <Route path="forms"                     element={<FormsPage />} />
        <Route path="rubrics"                   element={<RubricsPage />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
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
