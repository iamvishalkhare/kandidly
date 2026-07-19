/**
 * Shared sidebar layout for all /console pages.
 * Determines active nav item from the current URL.
 */

import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
  MessageSquare,
  Send,
  // BookOpen,   // re-enable with the Rubrics nav item
  // BarChart3,  // re-enable with the Analytics nav item
  ChevronRight,
  Plus,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { getUser } from '../../lib/auth';
import { useConsoleMe } from '../../lib/consoleApi';
import AccountModal, { Avatar } from './AccountModal';

const NAV_ITEMS = [
  { label: 'Dashboard',    icon: LayoutDashboard, href: '/console',              exact: true },
  { label: 'Requisitions', icon: Briefcase,       href: '/console/requisitions', exact: false },
  { label: 'Interviews',   icon: MessageSquare,   href: '/console/interviews',   exact: false },
  { label: 'Invitations',  icon: Send,            href: '/console/invitations',  exact: false },
  // Hidden until these sections have real content — uncomment to restore
  // (also restore the BookOpen / BarChart3 imports above).
  // { label: 'Rubrics',      icon: BookOpen,        href: '/console/rubrics',      exact: false },
  // { label: 'Analytics',    icon: BarChart3,       href: '/console/analytics',    exact: false },
] as const;

/** Sidebar footer: the signed-in user; opens the account/usage/logout modal. */
function UserChip({ onClick }: { onClick: () => void }) {
  const { data: me } = useConsoleMe();
  const stored = getUser(); // localStorage fallback while /me loads
  const name = me?.name ?? stored?.email?.split('@')[0] ?? 'Account';
  const email = me?.email ?? stored?.email ?? '';
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-container transition-colors duration-150 group"
    >
      <Avatar name={me?.name} email={email} avatarUrl={me?.avatar_url} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-on-surface truncate">{name}</p>
        <p className="font-mono text-xs text-on-surface-variant truncate">{email}</p>
      </div>
      <ChevronRight
        size={14}
        className="shrink-0 text-on-surface-variant group-hover:text-on-surface transition-colors duration-150"
      />
    </button>
  );
}

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [accountOpen, setAccountOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-surface-container-lowest">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 bg-surface-container-lowest border-r border-outline-variant flex flex-col">
        {/* Brand */}
        <Link to="/console" className="p-5 border-b border-outline-variant block">
          <p className="font-display text-lg font-bold text-primary-fixed-dim leading-tight">KANDIDLY AI</p>
          <p className="label-mono text-on-surface-variant mt-0.5">Intelligent Interviews</p>
        </Link>

        {/* CTA */}
        <div className="p-4 border-b border-outline-variant">
          <Link
            to="/console/requisitions/new"
            className="flex items-center justify-center gap-2 w-full py-2.5 bg-primary-container text-on-primary-container label-mono font-bold border border-primary-container hover:bg-transparent hover:text-primary-fixed-dim transition-colors duration-150"
          >
            <Plus size={14} />
            New Requisition
          </Link>
        </div>

        {/* Primary nav */}
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon;
            const isActive = item.exact
              ? location.pathname === item.href
              : location.pathname.startsWith(item.href);
            return (
              <Link
                key={item.label}
                to={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5 label-mono transition-colors duration-150',
                  isActive
                    ? 'bg-primary-container text-on-primary-container'
                    : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container'
                )}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Signed-in user */}
        <div className="px-3 pb-4 border-t border-outline-variant pt-3">
          <UserChip onClick={() => setAccountOpen(true)} />
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto flex flex-col">{children}</main>

      <AccountModal open={accountOpen} onClose={() => setAccountOpen(false)} />
    </div>
  );
}
