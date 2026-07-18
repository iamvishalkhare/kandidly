/**
 * Profile / settings dialog opened from the sidebar user chip.
 * claude.ai-console layout: blurred backdrop, section list on the left
 * (Account, Usage; Log out pinned at the bottom), detail pane on the right.
 */

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { BarChart3, LogOut, User as UserIcon, X } from 'lucide-react';
import { authApi } from '../../lib/api';
import { clearAuth } from '../../lib/auth';
import { useConsoleMe, useConsoleUsage } from '../../lib/consoleApi';
import { cn } from '../../lib/utils';
import { Spinner } from '../../components/ui';
import type { AccountOut, UsageOut } from '../../lib/types';

type Section = 'account' | 'usage';

const SECTIONS: { id: Section; label: string; icon: typeof UserIcon }[] = [
  { id: 'account', label: 'Account', icon: UserIcon },
  { id: 'usage',   label: 'Usage',   icon: BarChart3 },
];

export function Avatar({
  name,
  email,
  avatarUrl,
  className,
}: {
  name?: string | null;
  email?: string | null;
  avatarUrl?: string | null;
  className?: string;
}) {
  const initials = (name || email || '?')
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0]!.toUpperCase())
    .join('');
  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name ?? 'Profile picture'}
        className={cn('size-9 shrink-0 object-cover border border-outline-variant', className)}
      />
    );
  }
  return (
    <div
      className={cn(
        'size-9 shrink-0 flex items-center justify-center border border-outline-variant bg-surface font-display font-bold text-primary-fixed-dim',
        className,
      )}
    >
      {initials}
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 px-4 py-3 border-b border-outline-variant last:border-b-0">
      <span className="label-mono text-on-surface-variant">{label}</span>
      <span className="text-sm text-on-surface text-right truncate">{value}</span>
    </div>
  );
}

function AccountSection({ me }: { me: AccountOut | undefined }) {
  if (!me) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size={20} />
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-4 p-4 border border-outline-variant bg-surface">
        <Avatar name={me.name} email={me.email} avatarUrl={me.avatar_url} className="size-12 text-lg" />
        <div className="min-w-0">
          <p className="font-display font-bold text-on-surface leading-tight truncate">{me.name}</p>
          <p className="font-mono text-xs text-on-surface-variant mt-0.5 truncate">{me.email}</p>
        </div>
      </div>
      <div className="border border-outline-variant">
        <FieldRow label="Organization" value={me.org_name} />
        <FieldRow label="Name" value={me.name} />
        <FieldRow label="Email" value={me.email} />
        <FieldRow label="Role" value={<span className="capitalize">{me.role}</span>} />
        <FieldRow label="Plan" value={<span className="capitalize">{me.plan} plan</span>} />
      </div>
    </div>
  );
}

function UsageMeter({
  label,
  hint,
  used,
  limit,
}: {
  label: string;
  hint: string;
  used: number;
  limit: number;
}) {
  const atLimit = used >= limit;
  const pct = Math.min(100, limit > 0 ? (used / limit) * 100 : 100);
  return (
    <div className="p-4 border border-outline-variant bg-surface space-y-2.5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm font-medium text-on-surface">{label}</p>
        <p className={cn('label-mono', atLimit ? 'text-error' : 'text-on-surface-variant')}>
          {used} / {limit}
        </p>
      </div>
      <div className="h-1.5 bg-surface-container-high">
        <div
          className={cn('h-full transition-all duration-300', atLimit ? 'bg-error' : 'bg-primary-container')}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-on-surface-variant">{hint}</p>
    </div>
  );
}

function UsageSection({ usage }: { usage: UsageOut | undefined }) {
  if (!usage) {
    return (
      <div className="flex justify-center py-12">
        <Spinner size={20} />
      </div>
    );
  }
  const reqsMaxed = usage.requisitions_used >= usage.requisitions_limit;
  const interviewsMaxed = usage.interviews_used >= usage.interviews_limit;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between p-4 border border-outline-variant bg-surface">
        <div>
          <p className="text-sm font-medium text-on-surface capitalize">{usage.plan} plan</p>
          <p className="text-xs text-on-surface-variant mt-0.5">
            Includes {usage.requisitions_limit} requisitions and {usage.interviews_limit} interviews in total.
          </p>
        </div>
        <span className="label-mono px-2 py-1 bg-primary-container text-on-primary-container">
          {usage.plan}
        </span>
      </div>
      <UsageMeter
        label="Requisitions"
        hint={`Deployed interview requisitions. Your plan allows ${usage.requisitions_limit}.`}
        used={usage.requisitions_used}
        limit={usage.requisitions_limit}
      />
      <UsageMeter
        label="Interviews"
        hint={`Candidate interviews taken across all requisitions, cumulatively. Your plan allows ${usage.interviews_limit}.`}
        used={usage.interviews_used}
        limit={usage.interviews_limit}
      />
      {(reqsMaxed || interviewsMaxed) && (
        <p className="text-xs text-error border border-error/40 bg-error/10 px-3 py-2.5">
          You have reached your free plan limit. Please upgrade to deploy more interviews.
        </p>
      )}
    </div>
  );
}

export default function AccountModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [section, setSection] = useState<Section>('account');
  const [loggingOut, setLoggingOut] = useState(false);
  const queryClient = useQueryClient();
  const { data: me } = useConsoleMe();
  const { data: usage } = useConsoleUsage();

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    let logoutUrl: string | null = null;
    try {
      // Revoke the token server-side; even if unreachable, still clear locally.
      const res = await authApi.logout('/');
      logoutUrl = res.logout_url ?? null;
    } catch {
      /* best-effort */
    }
    queryClient.clear();
    clearAuth();
    // Hard replace: wipes in-memory state and keeps the console out of history.
    // Route through WorkOS's own logout when available so its SSO cookie
    // actually dies too — otherwise the next sign-in silently reuses it.
    window.location.replace(logoutUrl || '/');
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Account settings"
      onClick={onClose}
    >
      {/* Blurred backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />

      {/* Panel */}
      <div
        className="relative w-full max-w-2xl h-[480px] max-h-[85vh] flex border border-outline-variant bg-surface-container-lowest shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Section list */}
        <aside className="w-48 shrink-0 border-r border-outline-variant flex flex-col">
          <p className="label-mono text-on-surface-variant px-4 pt-4 pb-2">Settings</p>
          <nav className="px-2 space-y-0.5 flex-1">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setSection(id)}
                className={cn(
                  'w-full flex items-center gap-2.5 px-3 py-2.5 label-mono transition-colors duration-150',
                  section === id
                    ? 'bg-primary-container text-on-primary-container'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container',
                )}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </nav>
          <div className="p-2 border-t border-outline-variant">
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 label-mono text-error hover:bg-error/10 transition-colors duration-150 disabled:opacity-60"
            >
              {loggingOut ? <Spinner size={15} /> : <LogOut size={15} />}
              {loggingOut ? 'Logging out…' : 'Log out'}
            </button>
          </div>
        </aside>

        {/* Detail pane */}
        <section className="flex-1 min-w-0 flex flex-col">
          <header className="flex items-center justify-between px-5 py-4 border-b border-outline-variant">
            <h2 className="font-display font-bold text-on-surface">
              {SECTIONS.find(s => s.id === section)?.label}
            </h2>
            <button
              onClick={onClose}
              aria-label="Close settings"
              className="p-1 text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors duration-150"
            >
              <X size={16} />
            </button>
          </header>
          <div className="flex-1 overflow-y-auto p-5">
            {section === 'account' ? <AccountSection me={me} /> : <UsageSection usage={usage} />}
          </div>
        </section>
      </div>
    </div>
  );
}
