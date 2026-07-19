/**
 * /console/interviews — completed interview ledger with requisition-aware filters.
 */

import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, CalendarClock, Filter, RotateCcw, Search, SlidersHorizontal, Trash2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { isOperator } from '../../lib/auth';
import { useToast } from '../../components/ui';
import ConsoleLayout from './ConsoleLayout';
import { AutocompleteFilter, DropdownFilter } from './filters';
import type { InterviewDecision } from './interviewData';
import { useConsoleInterviews, useDeleteInterview } from '../../lib/consoleApi';

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

function getParam(searchParams: URLSearchParams, key: string) {
  return searchParams.get(key) ?? '';
}

function toDateTimeInputValue(value: string) {
  return value ? value.slice(0, 16) : '';
}

const DECISION_CHIP_CLASS: Record<InterviewDecision, string> = {
  Shortlist: 'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]',
  Hold: 'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
  Reject: 'border-[var(--red-chip-text)] bg-[var(--red-chip-bg)] text-[var(--red-chip-text)]',
};

function DecisionPill({ decision }: { decision: InterviewDecision }) {
  return (
    <span className={cn('inline-flex border px-2 py-1 label-mono', DECISION_CHIP_CLASS[decision])}>
      {decision}
    </span>
  );
}

export default function ConsoleInterviews() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: interviews = [], isLoading } = useConsoleInterviews();
  const { toast } = useToast();
  const deleteInterview = useDeleteInterview();
  // Operator-only in prod before it's considered safe to open up to every
  // console user (matches the backend gate, backend/app/api/console.py).
  const canDeleteInterviews = isOperator();

  const handleDelete = (id: string, candidateName: string) => {
    if (deleteInterview.isPending) return;
    if (!window.confirm(`Permanently delete ${candidateName}'s interview? This removes its recording, transcript, and score, and lets the candidate attempt the invite again. This cannot be undone.`)) {
      return;
    }
    deleteInterview.mutate(id, {
      onSuccess: () => toast('Interview deleted.', 'success'),
      onError: () => toast('Deleting the interview failed. Please try again.', 'error'),
    });
  };

  const requisitionIdFilter = getParam(searchParams, 'requisitionId');
  const requisitionTitleFilter = getParam(searchParams, 'requisitionTitle');
  const domainFilter = getParam(searchParams, 'domain');
  const scoringStatusFilter = getParam(searchParams, 'scoringStatus');
  const decisionFilter = getParam(searchParams, 'decision');
  const startFilter = getParam(searchParams, 'start');
  const endFilter = getParam(searchParams, 'end');
  const searchFilter = getParam(searchParams, 'q');

  const requisitionIds = useMemo(
    () => Array.from(new Set(interviews.map(row => row.requisitionId))).sort((a, b) => a.localeCompare(b)),
    [interviews],
  );
  const requisitionTitles = useMemo(
    () => Array.from(new Set(interviews.map(row => row.requisitionTitle))).sort((a, b) => a.localeCompare(b)),
    [interviews],
  );
  const domains = useMemo(
    () => Array.from(new Set(interviews.map(row => row.domain))).sort((a, b) => a.localeCompare(b)),
    [interviews],
  );

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim().length > 0) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };

  const clearFilters = () => {
    setSearchParams({}, { replace: true });
  };

  const filtered = interviews.filter(interview => {
    const searchTerm = searchFilter.trim().toLowerCase();
    const concludedAt = new Date(interview.concludedAt).getTime();
    const startsAt = startFilter ? new Date(startFilter).getTime() : Number.NEGATIVE_INFINITY;
    const endsAt = endFilter ? new Date(endFilter).getTime() : Number.POSITIVE_INFINITY;

    const matchesSearch =
      searchTerm.length === 0 ||
      interview.candidateName.toLowerCase().includes(searchTerm) ||
      interview.requisitionId.toLowerCase().includes(searchTerm) ||
      interview.requisitionTitle.toLowerCase().includes(searchTerm) ||
      interview.domain.toLowerCase().includes(searchTerm);
    const matchesRequisitionId =
      requisitionIdFilter.length === 0 ||
      interview.requisitionId.toLowerCase().includes(requisitionIdFilter.toLowerCase());
    const matchesRequisitionTitle =
      requisitionTitleFilter.length === 0 ||
      interview.requisitionTitle.toLowerCase().includes(requisitionTitleFilter.toLowerCase());
    const matchesDomain =
      domainFilter.length === 0 ||
      interview.domain.toLowerCase().includes(domainFilter.toLowerCase());
    const matchesScoringStatus =
      scoringStatusFilter.length === 0 || interview.scoringStatus === scoringStatusFilter;
    const matchesDecision =
      decisionFilter.length === 0 || interview.decision === decisionFilter;
    const matchesDateRange = concludedAt >= startsAt && concludedAt <= endsAt;

    return (
      matchesSearch &&
      matchesRequisitionId &&
      matchesRequisitionTitle &&
      matchesDomain &&
      matchesScoringStatus &&
      matchesDecision &&
      matchesDateRange
    );
  });

  const hasFilters = Array.from(searchParams.keys()).length > 0;
  const doneCount = filtered.filter(interview => interview.scoringStatus === 'Done').length;
  const evaluatingCount = filtered.length - doneCount;

  return (
    <ConsoleLayout>
      <header className="border-b border-outline-variant bg-surface px-4 py-4 sticky top-0 z-30">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h1 className="font-display text-headline-lg text-on-surface tracking-tight">Interviews</h1>
            <p className="label-mono text-on-surface-variant mt-1">
              {filtered.length} visible · {doneCount} done · {evaluatingCount} evaluating
            </p>
          </div>
          <div className="flex flex-col gap-2 md:flex-row md:items-center">
            <div className="relative h-10 w-full md:w-72 flex items-center border border-outline-variant bg-surface-container-lowest focus-within:border-primary-container transition-colors">
              <Search size={16} className="absolute left-3 text-on-surface-variant" />
              <input
                type="text"
                value={searchFilter}
                onChange={e => setFilter('q', e.target.value)}
                placeholder="SEARCH CANDIDATES..."
                className="w-full h-full bg-transparent border-none text-on-surface font-mono text-xs uppercase tracking-[0.15em] pl-10 pr-3 focus:outline-none focus:ring-0 placeholder:text-on-surface-variant"
              />
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
              <p className="label-mono text-on-surface">Filter Interviews</p>
            </div>
            {requisitionIdFilter && (
              <span className="label-mono text-primary-fixed-dim border border-primary-container px-2 py-1">
                Requisition {requisitionIdFilter}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-7 gap-px bg-outline-variant">
            <div className="bg-surface p-4">
              <AutocompleteFilter
                label="Requisition ID"
                value={requisitionIdFilter}
                options={requisitionIds}
                placeholder="REQ ID"
                onChange={value => setFilter('requisitionId', value)}
              />
            </div>
            <div className="bg-surface p-4">
              <AutocompleteFilter
                label="Job Title"
                value={requisitionTitleFilter}
                options={requisitionTitles}
                placeholder="JOB TITLE"
                onChange={value => setFilter('requisitionTitle', value)}
              />
            </div>
            <div className="bg-surface p-4">
              <AutocompleteFilter
                label="Domain"
                value={domainFilter}
                options={domains}
                placeholder="DOMAIN"
                onChange={value => setFilter('domain', value)}
              />
            </div>
            <div className="bg-surface p-4">
              <DropdownFilter
                label="Scoring Status"
                value={scoringStatusFilter}
                placeholder="All Statuses"
                options={[
                  { value: 'Evaluating', label: 'Evaluating' },
                  { value: 'Done', label: 'Done' },
                ]}
                onChange={value => setFilter('scoringStatus', value)}
              />
            </div>
            <div className="bg-surface p-4">
              <DropdownFilter
                label="Decision"
                value={decisionFilter}
                placeholder="All Decisions"
                options={[
                  { value: 'Shortlist', label: 'Shortlist' },
                  { value: 'Hold', label: 'Hold' },
                  { value: 'Reject', label: 'Reject' },
                ]}
                onChange={value => setFilter('decision', value)}
              />
            </div>
            <label className="block bg-surface p-4">
              <span className="label-mono text-on-surface-variant mb-2 flex items-center gap-2">
                <CalendarClock size={14} />
                From
              </span>
              <input
                type="datetime-local"
                value={toDateTimeInputValue(startFilter)}
                onChange={e => setFilter('start', e.target.value)}
                className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs uppercase tracking-[0.08em] focus:outline-none focus:border-primary-container"
              />
            </label>
            <label className="block bg-surface p-4">
              <span className="label-mono text-on-surface-variant mb-2 flex items-center gap-2">
                <CalendarClock size={14} />
                To
              </span>
              <input
                type="datetime-local"
                value={toDateTimeInputValue(endFilter)}
                onChange={e => setFilter('end', e.target.value)}
                className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs uppercase tracking-[0.08em] focus:outline-none focus:border-primary-container"
              />
            </label>
          </div>
        </section>

        <section className="border border-outline-variant bg-surface">
          <div className="grid grid-cols-[1.3fr_1fr_1.5fr_1fr_1fr_1fr_1.3fr] border-b border-outline-variant bg-surface-container-lowest text-on-surface-variant label-mono">
            <div className="px-4 py-3">Candidate</div>
            <div className="px-4 py-3 border-l border-outline-variant">Requisition ID</div>
            <div className="px-4 py-3 border-l border-outline-variant">Job Title</div>
            <div className="px-4 py-3 border-l border-outline-variant">Domain</div>
            <div className="px-4 py-3 border-l border-outline-variant">Scoring</div>
            <div className="px-4 py-3 border-l border-outline-variant">Decision</div>
            <div className="px-4 py-3 border-l border-outline-variant">Interview Taken On</div>
          </div>

          <div className="divide-y divide-outline-variant">
            {filtered.map(interview => (
              <Link
                key={interview.id}
                to={`/console/interviews/${interview.id}`}
                className="grid grid-cols-1 xl:grid-cols-[1.3fr_1fr_1.5fr_1fr_1fr_1fr_1.3fr] bg-surface hover:bg-surface-container transition-colors duration-150"
              >
                <div className="px-4 py-4">
                  <p className="font-medium text-on-surface">{interview.candidateName}</p>
                  {interview.candidateEmail && (
                    <p className="text-sm text-on-surface-variant mt-0.5 break-all">
                      {interview.candidateEmail}
                    </p>
                  )}
                  <p className="label-mono text-on-surface-variant mt-1">{interview.code.toUpperCase()}</p>
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant label-mono text-primary-fixed-dim">
                  {interview.requisitionId}
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant text-on-surface">
                  {interview.requisitionTitle}
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant text-on-surface-variant">
                  {interview.domain}
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant">
                  <span
                    className={cn(
                      'inline-flex border px-2 py-1 label-mono',
                      interview.scoringStatus === 'Done'
                        ? 'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]'
                        : 'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
                    )}
                  >
                    {interview.scoringStatus}
                  </span>
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant">
                  {interview.decision ? (
                    <DecisionPill decision={interview.decision} />
                  ) : (
                    <span className="label-mono text-on-surface-variant">—</span>
                  )}
                </div>
                <div className="px-4 py-4 xl:border-l xl:border-outline-variant label-mono text-on-surface-variant tabular flex items-center justify-between gap-3">
                  <span>{dateTimeFormatter.format(new Date(interview.concludedAt))}</span>
                  <span className="flex items-center gap-2 shrink-0">
                    {canDeleteInterviews && (
                      <button
                        type="button"
                        title="Delete this interview"
                        onClick={e => {
                          e.preventDefault();
                          e.stopPropagation();
                          handleDelete(interview.id, interview.candidateName);
                        }}
                        disabled={deleteInterview.isPending}
                        className="p-1 text-on-surface-variant hover:text-[var(--error)] transition-colors duration-150 disabled:opacity-50"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                    <ArrowRight size={16} className="text-text-muted" />
                  </span>
                </div>
              </Link>
            ))}
          </div>

          {filtered.length === 0 && (
            <div className="py-16 flex flex-col items-center gap-2 text-center">
              <Filter size={20} className="text-on-surface-variant" />
              <p className="label-mono text-on-surface-variant">
                {isLoading ? 'Loading interviews…' : 'No interviews match the active filters.'}
              </p>
            </div>
          )}
        </section>
      </div>
    </ConsoleLayout>
  );
}
