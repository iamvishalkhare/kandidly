/**
 * /console/invitations — org-wide invitations ledger (every guest-list row
 * across requisitions), server-side filtered + paginated. The Req ID cell
 * links to the requisition builder; revoke reuses the guest-list endpoint.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowRight,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Filter,
  RotateCcw,
  Search,
  SlidersHorizontal,
  UserX,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useToast } from '../../components/ui';
import ConsoleLayout from './ConsoleLayout';
import { AutocompleteFilter, DropdownFilter } from './filters';
import {
  useConsoleInvitations,
  useConsoleRequisitions,
  useRevokeInvitation,
  type InvitationRowWire,
} from '../../lib/consoleApi';

const PAGE_SIZE = 20;

const STATUS_LABELS: Record<InvitationRowWire['status'], string> = {
  invited: 'Invited',
  claimed: 'Attempting',
  completed: 'Done',
};

const STATUS_CHIP_CLASS: Record<InvitationRowWire['status'], string> = {
  invited: 'border-outline-variant bg-surface-container-lowest text-on-surface-variant',
  claimed: 'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
  completed: 'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]',
};

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function getParam(searchParams: URLSearchParams, key: string) {
  return searchParams.get(key) ?? '';
}

function candidateName(row: InvitationRowWire): string {
  return `${row.first_name} ${row.last_name}`.trim() || '—';
}

/** datetime-local value (local time) → ISO UTC for the API; '' → undefined. */
function toIsoUtc(value: string): string | undefined {
  return value ? new Date(value).toISOString() : undefined;
}

export default function ConsoleInvitations() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();
  const revokeInvitation = useRevokeInvitation();

  const searchFilter = getParam(searchParams, 'q');
  const reqCodeFilter = getParam(searchParams, 'req');
  const statusFilter = getParam(searchParams, 'status');
  const accessFilter = getParam(searchParams, 'access') || 'active';
  const startFilter = getParam(searchParams, 'start');
  const endFilter = getParam(searchParams, 'end');
  const page = Math.max(1, Number(getParam(searchParams, 'page')) || 1);

  // The search input is live-debounced into the `q` URL param; suggestions
  // come from the already-fetched page (the query itself is the search).
  const [searchDraft, setSearchDraft] = useState(searchFilter);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const setFilter = (key: string, value: string, { keepPage = false } = {}) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim().length > 0) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    if (!keepPage) next.delete('page'); // any filter change restarts at page 1
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchDraft !== searchFilter) setFilter('q', searchDraft);
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  const query = useMemo(
    () => ({
      q: searchFilter || undefined,
      requisitionCode: reqCodeFilter || undefined,
      status: (statusFilter || undefined) as 'invited' | 'claimed' | 'completed' | undefined,
      access: accessFilter as 'active' | 'revoked',
      createdAfter: toIsoUtc(startFilter),
      createdBefore: toIsoUtc(endFilter),
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }),
    [searchFilter, reqCodeFilter, statusFilter, accessFilter, startFilter, endFilter, page],
  );
  const { data, isLoading, isPlaceholderData } = useConsoleInvitations(query);
  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const { data: requisitions = [] } = useConsoleRequisitions();
  const requisitionCodes = useMemo(
    () => Array.from(new Set(requisitions.map(r => r.code))).sort((a, b) => a.localeCompare(b)),
    [requisitions],
  );

  const suggestions = rows.slice(0, 5);
  const showSuggestions =
    suggestOpen && searchDraft.trim().length > 0 && suggestions.length > 0 && !isLoading;

  const hasFilters = Array.from(searchParams.keys()).some(key => key !== 'page');

  const clearFilters = () => {
    setSearchDraft('');
    setSearchParams({}, { replace: true });
  };

  const setPage = (next: number) => {
    const params = new URLSearchParams(searchParams);
    if (next <= 1) params.delete('page');
    else params.set('page', String(next));
    setSearchParams(params, { replace: true });
  };

  const handleRevoke = (row: InvitationRowWire) => {
    if (revokeInvitation.isPending) return;
    if (
      !window.confirm(
        `Revoke ${candidateName(row) === '—' ? row.email : candidateName(row)}'s access to ${row.requisition_code}? They will no longer be able to start this interview. An interview already in progress is not affected.`,
      )
    ) {
      return;
    }
    revokeInvitation.mutate(
      { reqId: row.requisition_id, inviteId: row.id },
      {
        onSuccess: () => toast('Invitation revoked.', 'success'),
        onError: () => toast('Revoking the invitation failed. Please try again.', 'error'),
      },
    );
  };

  return (
    <ConsoleLayout>
      <header className="border-b border-outline-variant bg-surface px-4 py-4 sticky top-0 z-30">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h1 className="font-display text-headline-lg text-on-surface tracking-tight">Invitations</h1>
            <p className="label-mono text-on-surface-variant mt-1">
              {total} {accessFilter === 'revoked' ? 'revoked' : 'active'} invitation{total === 1 ? '' : 's'}
              {pageCount > 1 && ` · page ${Math.min(page, pageCount)} of ${pageCount}`}
            </p>
          </div>
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <div className="relative h-10 w-full md:w-72">
              <div className="h-full flex items-center border border-outline-variant bg-surface-container-lowest focus-within:border-primary-container transition-colors">
                <Search size={16} className="absolute left-3 text-on-surface-variant" />
                <input
                  ref={searchRef}
                  type="text"
                  value={searchDraft}
                  onChange={e => {
                    setSearchDraft(e.target.value);
                    setSuggestOpen(true);
                  }}
                  onFocus={() => setSuggestOpen(true)}
                  onBlur={() => setSuggestOpen(false)}
                  placeholder="SEARCH NAME OR EMAIL..."
                  className="w-full h-full bg-transparent border-none text-on-surface font-mono text-xs uppercase tracking-[0.15em] pl-10 pr-3 focus:outline-none focus:ring-0 placeholder:text-on-surface-variant"
                />
              </div>
              {showSuggestions && (
                <div className="absolute left-0 right-0 top-full mt-1 z-40 border border-outline-variant bg-surface shadow-xl max-h-72 overflow-y-auto">
                  {suggestions.map(row => (
                    <button
                      key={row.id}
                      type="button"
                      onMouseDown={e => e.preventDefault()}
                      onClick={() => {
                        setSearchDraft(row.email);
                        setFilter('q', row.email);
                        setSuggestOpen(false);
                        searchRef.current?.blur();
                      }}
                      className="w-full text-left px-3 py-2 hover:bg-surface-container transition-colors duration-75"
                    >
                      <p className="text-body-md text-on-surface">{candidateName(row)}</p>
                      <p className="font-mono text-xs text-on-surface-variant break-all">{row.email}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={clearFilters}
              disabled={!hasFilters}
              className={cn(
                'h-10 px-4 border label-mono flex items-center justify-center gap-2 transition-colors duration-150',
                hasFilters
                  ? 'border-outline-variant text-on-surface-variant hover:bg-surface-container hover:text-on-surface'
                  : 'border-outline-variant text-outline cursor-not-allowed opacity-50',
              )}
            >
              <RotateCcw size={16} />
              Reset
            </button>
          </div>
        </div>
      </header>

      <div className="p-4 flex-1 space-y-4">
        <section className="border border-outline-variant bg-surface">
          <div className="border-b border-outline-variant px-4 py-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <SlidersHorizontal size={16} className="text-primary-fixed-dim" />
              <p className="label-mono text-on-surface">Filter Invitations</p>
            </div>
            {reqCodeFilter && (
              <span className="label-mono text-primary-fixed-dim border border-primary-container px-2 py-1">
                Requisition {reqCodeFilter}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-px bg-outline-variant">
            <div className="bg-surface p-4">
              <AutocompleteFilter
                label="Requisition ID"
                value={reqCodeFilter}
                options={requisitionCodes}
                placeholder="REQ ID"
                onChange={value => setFilter('req', value)}
              />
            </div>
            <div className="bg-surface p-4">
              <DropdownFilter
                label="Status"
                value={statusFilter}
                placeholder="All Statuses"
                options={[
                  { value: 'invited', label: 'Invited' },
                  { value: 'claimed', label: 'Attempting' },
                  { value: 'completed', label: 'Done' },
                ]}
                onChange={value => setFilter('status', value)}
              />
            </div>
            <div className="bg-surface p-4">
              <DropdownFilter
                label="Access"
                value={accessFilter}
                placeholder="Active"
                clearable={false}
                options={[
                  { value: 'active', label: 'Active' },
                  { value: 'revoked', label: 'Revoked' },
                ]}
                onChange={value => setFilter('access', value === 'active' ? '' : value)}
              />
            </div>
            <label className="block bg-surface p-4">
              <span className="label-mono text-on-surface-variant mb-2 flex items-center gap-2">
                <CalendarClock size={14} />
                Invited From
              </span>
              <input
                type="datetime-local"
                value={startFilter}
                onChange={e => setFilter('start', e.target.value)}
                className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs uppercase tracking-[0.08em] focus:outline-none focus:border-primary-container"
              />
            </label>
            <label className="block bg-surface p-4">
              <span className="label-mono text-on-surface-variant mb-2 flex items-center gap-2">
                <CalendarClock size={14} />
                Invited To
              </span>
              <input
                type="datetime-local"
                value={endFilter}
                onChange={e => setFilter('end', e.target.value)}
                className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs uppercase tracking-[0.08em] focus:outline-none focus:border-primary-container"
              />
            </label>
          </div>
        </section>

        <section className={cn('border border-outline-variant bg-surface', isPlaceholderData && 'opacity-60')}>
          <div className="hidden xl:grid grid-cols-[1.2fr_1.5fr_1fr_1fr_1.2fr_1fr] border-b border-outline-variant bg-surface-container-lowest text-on-surface-variant label-mono">
            <div className="px-4 py-3">Candidate</div>
            <div className="px-4 py-3 border-l border-outline-variant">Email</div>
            <div className="px-4 py-3 border-l border-outline-variant">Requisition ID</div>
            <div className="px-4 py-3 border-l border-outline-variant">Status</div>
            <div className="px-4 py-3 border-l border-outline-variant">Invited On</div>
            <div className="px-4 py-3 border-l border-outline-variant">Access</div>
          </div>

          <div className="divide-y divide-outline-variant">
            {rows.map(row => (
              <div
                key={row.id}
                className="grid grid-cols-1 xl:grid-cols-[1.2fr_1.5fr_1fr_1fr_1.2fr_1fr] bg-surface hover:bg-surface-container transition-colors duration-150"
              >
                <div className="px-4 py-4">
                  <p className="font-medium text-on-surface">{candidateName(row)}</p>
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant text-on-surface-variant break-all">
                  {row.email}
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant">
                  <Link
                    to={`/console/requisitions/${row.requisition_id}`}
                    title={row.requisition_title}
                    className="label-mono text-primary-fixed-dim hover:underline inline-flex items-center gap-1"
                  >
                    {row.requisition_code}
                    <ArrowRight size={12} />
                  </Link>
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant">
                  <span className={cn('inline-flex border px-2 py-1 label-mono', STATUS_CHIP_CLASS[row.status])}>
                    {STATUS_LABELS[row.status]}
                  </span>
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant label-mono text-on-surface-variant tabular">
                  {dateTimeFormatter.format(new Date(row.created_at))}
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant">
                  {row.revoked_at ? (
                    <span className="label-mono text-on-surface-variant" title={dateTimeFormatter.format(new Date(row.revoked_at))}>
                      Revoked
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleRevoke(row)}
                      disabled={revokeInvitation.isPending}
                      className="inline-flex items-center gap-2 border border-outline-variant px-2 py-1 label-mono text-on-surface-variant hover:border-[var(--error)] hover:text-[var(--error)] transition-colors duration-150 disabled:opacity-50"
                    >
                      <UserX size={14} />
                      Revoke
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {rows.length === 0 && (
            <div className="py-16 flex flex-col items-center gap-2 text-center">
              <Filter size={20} className="text-on-surface-variant" />
              <p className="label-mono text-on-surface-variant">
                {isLoading
                  ? 'Loading invitations…'
                  : hasFilters
                    ? 'No invitations match the active filters.'
                    : 'No invitations yet — add candidates to an invite-only requisition.'}
              </p>
            </div>
          )}

          {total > PAGE_SIZE && (
            <div className="border-t border-outline-variant px-4 py-3 flex items-center justify-between">
              <p className="label-mono text-on-surface-variant">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPage(page - 1)}
                  disabled={page <= 1}
                  className="h-8 px-3 border border-outline-variant label-mono flex items-center gap-1 text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft size={14} />
                  Prev
                </button>
                <span className="label-mono text-on-surface-variant tabular">
                  {Math.min(page, pageCount)} / {pageCount}
                </span>
                <button
                  type="button"
                  onClick={() => setPage(page + 1)}
                  disabled={page >= pageCount}
                  className="h-8 px-3 border border-outline-variant label-mono flex items-center gap-1 text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </ConsoleLayout>
  );
}
