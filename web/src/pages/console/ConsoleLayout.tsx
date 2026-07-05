/**
 * Shared sidebar layout for all /console pages.
 * Determines active nav item from the current URL.
 */

import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
  MessageSquare,
  BookOpen,
  BarChart3,
  Settings,
  HelpCircle,
  Plus,
} from 'lucide-react';
import { cn } from '../../lib/utils';

const NAV_ITEMS = [
  { label: 'Dashboard',    icon: LayoutDashboard, href: '/console',              exact: true },
  { label: 'Requisitions', icon: Briefcase,       href: '/console/requisitions', exact: false },
  { label: 'Interviews',   icon: MessageSquare,   href: '/console/interviews',   exact: false },
  { label: 'Rubrics',      icon: BookOpen,        href: '/console/rubrics',      exact: false },
  { label: 'Analytics',    icon: BarChart3,       href: '/console/analytics',    exact: false },
] as const;

const BOTTOM_NAV = [
  { label: 'Settings', icon: Settings,    href: '/console' },
  { label: 'Support',  icon: HelpCircle,  href: '/console' },
] as const;

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  return (
    <div className="flex min-h-screen bg-surface-container-lowest">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 bg-surface-container-lowest border-r border-outline-variant flex flex-col">
        {/* Brand */}
        <Link to="/console" className="p-5 border-b border-outline-variant block">
          <p className="font-display text-lg font-bold text-primary-fixed-dim leading-tight">KANDIDLY AI</p>
          <p className="label-mono text-on-surface-variant mt-0.5">Voice Console</p>
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

        {/* Bottom nav */}
        <div className="px-3 pb-4 space-y-0.5 border-t border-outline-variant pt-3">
          {BOTTOM_NAV.map(item => {
            const Icon = item.icon;
            return (
              <Link
                key={item.label}
                to={item.href}
                className="flex items-center gap-3 px-3 py-2.5 label-mono text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors duration-150"
              >
                <Icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto flex flex-col">{children}</main>
    </div>
  );
}
