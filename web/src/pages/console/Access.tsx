/**
 * /console/access — operator-only console-access allowlist. Kandidly is
 * invite-only: only emails on this list (plus the operator, always) can sign
 * in to the console. Interview access is unaffected — that's governed per
 * requisition (open link or guest list). Backend 403s every other account;
 * the client-side gate here only hides the page from non-operators.
 */

import { useState } from 'react';
import { KeyRound, Lock, ShieldCheck, Trash2, UserPlus } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useToast } from '../../components/ui';
import { isOperator } from '../../lib/auth';
import ConsoleLayout from './ConsoleLayout';
import { useAllowlist, useAllowlistMutations, type AllowlistEntryWire } from '../../lib/consoleApi';

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function ConsoleAccess() {
  const operator = isOperator();
  const { toast } = useToast();
  const { data, isLoading } = useAllowlist(operator);
  const { add, remove } = useAllowlistMutations();
  const [draft, setDraft] = useState('');

  if (!operator) {
    return (
      <ConsoleLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center p-6">
          <Lock size={20} className="text-on-surface-variant" />
          <p className="label-mono text-on-surface-variant">
            Access management is not available for this account.
          </p>
        </div>
      </ConsoleLayout>
    );
  }

  const entries = data?.items ?? [];
  const email = draft.trim().toLowerCase();
  const valid = EMAIL_RE.test(email);

  const handleAdd = () => {
    if (!valid || add.isPending) return;
    add.mutate(email, {
      onSuccess: result => {
        toast(
          result.created
            ? `${result.entry.email} can now sign in to Kandidly.`
            : `${result.entry.email} is already on the list.`,
          'success',
        );
        setDraft('');
      },
      onError: () => toast('Adding the email failed. Please try again.', 'error'),
    });
  };

  const handleRemove = (entry: AllowlistEntryWire) => {
    if (remove.isPending) return;
    if (
      !window.confirm(
        `Remove ${entry.email} from the allowlist? They won't be able to sign in to the console again. A session that's already signed in stays valid until it expires.`,
      )
    ) {
      return;
    }
    remove.mutate(entry.id, {
      onSuccess: () => toast(`${entry.email} removed.`, 'success'),
      onError: () => toast('Removing the email failed. Please try again.', 'error'),
    });
  };

  return (
    <ConsoleLayout>
      <header className="border-b border-outline-variant bg-surface px-4 py-4 sticky top-0 z-30">
        <h1 className="font-display text-headline-lg text-on-surface tracking-tight">Access</h1>
        <p className="label-mono text-on-surface-variant mt-1">
          Kandidly is invite-only · {entries.length + 1} account{entries.length === 0 ? '' : 's'} can sign in
        </p>
      </header>

      <div className="p-4 flex-1 space-y-4">
        <section className="border border-outline-variant bg-surface">
          <div className="border-b border-outline-variant px-4 py-3 flex items-center gap-2">
            <UserPlus size={16} className="text-primary-fixed-dim" />
            <p className="label-mono text-on-surface">Grant console access</p>
          </div>
          <div className="p-4 flex flex-col gap-2 md:flex-row">
            <input
              type="email"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              placeholder="EMAIL ADDRESS…"
              className="h-10 w-full md:max-w-md border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs tracking-[0.08em] focus:outline-none focus:border-primary-container placeholder:text-on-surface-variant placeholder:uppercase"
            />
            <button
              type="button"
              onClick={handleAdd}
              disabled={!valid || add.isPending}
              className={cn(
                'h-10 px-4 border label-mono flex items-center justify-center gap-2 transition-colors duration-150',
                valid && !add.isPending
                  ? 'bg-primary-container text-on-primary-container border-primary-container hover:bg-transparent hover:text-primary-fixed-dim'
                  : 'border-outline-variant text-outline cursor-not-allowed opacity-50',
              )}
            >
              <KeyRound size={14} />
              Allow sign-in
            </button>
          </div>
          <p className="px-4 pb-4 text-body-md text-on-surface-variant">
            Anyone on this list can sign in and use the console with their own workspace. This
            doesn&apos;t send an email — share the link with them yourself. Interview links are
            unaffected: candidates never need console access.
          </p>
        </section>

        <section className="border border-outline-variant bg-surface">
          <div className="hidden md:grid grid-cols-[2fr_1.2fr_0.8fr] border-b border-outline-variant bg-surface-container-lowest text-on-surface-variant label-mono">
            <div className="px-4 py-3">Email</div>
            <div className="px-4 py-3 border-l border-outline-variant">Added on</div>
            <div className="px-4 py-3 border-l border-outline-variant">Access</div>
          </div>

          <div className="divide-y divide-outline-variant">
            {/* Operator row — implicit, cannot be removed. */}
            <div className="grid grid-cols-1 md:grid-cols-[2fr_1.2fr_0.8fr] bg-surface">
              <div className="px-4 py-4 flex items-center gap-2 break-all">
                <ShieldCheck size={14} className="shrink-0 text-primary-fixed-dim" />
                <span className="text-on-surface">{data?.operator_email ?? ''}</span>
              </div>
              <div className="px-4 py-4 md:border-l md:border-outline-variant label-mono text-on-surface-variant">
                —
              </div>
              <div className="px-4 py-4 md:border-l md:border-outline-variant">
                <span className="inline-flex border border-primary-container px-2 py-1 label-mono text-primary-fixed-dim">
                  Operator
                </span>
              </div>
            </div>

            {entries.map(entry => (
              <div
                key={entry.id}
                className="grid grid-cols-1 md:grid-cols-[2fr_1.2fr_0.8fr] bg-surface hover:bg-surface-container transition-colors duration-150"
              >
                <div className="px-4 py-4 text-on-surface break-all">{entry.email}</div>
                <div className="px-4 py-4 md:border-l md:border-outline-variant label-mono text-on-surface-variant tabular">
                  {dateTimeFormatter.format(new Date(entry.created_at))}
                </div>
                <div className="px-4 py-4 md:border-l md:border-outline-variant">
                  <button
                    type="button"
                    onClick={() => handleRemove(entry)}
                    disabled={remove.isPending}
                    className="inline-flex items-center gap-2 border border-outline-variant px-2 py-1 label-mono text-on-surface-variant hover:border-[var(--error)] hover:text-[var(--error)] transition-colors duration-150 disabled:opacity-50"
                  >
                    <Trash2 size={14} />
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          {entries.length === 0 && (
            <div className="py-12 flex flex-col items-center gap-2 text-center border-t border-outline-variant">
              <p className="label-mono text-on-surface-variant">
                {isLoading
                  ? 'Loading allowlist…'
                  : 'No one else has been invited yet — only the operator can sign in.'}
              </p>
            </div>
          )}
        </section>
      </div>
    </ConsoleLayout>
  );
}
