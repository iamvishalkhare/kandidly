/**
 * /console/requisitions — Requisition management grid.
 * Interlocking card grid with LIVE/OFFLINE toggles, search, and filters.
 */

import { useState, useCallback, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Check, Copy, Search, SlidersHorizontal, Plus } from 'lucide-react';
import { cn } from '../../lib/utils';
import ConsoleLayout from './ConsoleLayout';
import { copyToClipboard, getInterviewUrl, type Requisition } from './requisitionData';
import { useConsoleRequisitions, useToggleRequisitionStatus } from '../../lib/consoleApi';

type StatusFilter = 'all' | 'live' | 'offline';

/* -------------------------------------------------------------------------- */
/*  Requisition Card                                                          */
/* -------------------------------------------------------------------------- */

function ReqCard({
  req,
  onToggle,
}: {
  req: Requisition;
  onToggle: (id: string) => void;
}) {
  const navigate = useNavigate();
  const [flash, setFlash] = useState(false);
  const [copied, setCopied] = useState(false);
  const visibleRequirements = req.technicalRequirements.slice(0, 3);
  const hiddenRequirementCount = req.technicalRequirements.length - visibleRequirements.length;
  const interviewUrl = getInterviewUrl(req.interviewToken);

  const openRequisition = () => {
    navigate(`/console/requisitions/${req.id}`);
  };

  const handleToggle = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setFlash(true);
    onToggle(req.id);
    // Remove flash class after animation completes
    setTimeout(() => setFlash(false), 300);
  };

  const handleCopyInterviewUrl = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    await copyToClipboard(interviewUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const openCompletedInterviews = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    navigate(`/console/interviews?requisitionId=${encodeURIComponent(req.code)}`);
  };

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={openRequisition}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openRequisition();
        }
      }}
      className={cn(
        'bg-surface flex flex-col transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-container',
        !req.live && 'opacity-70',
        flash && 'ring-2 ring-inset ring-primary-container',
      )}
      style={{ minHeight: '320px' }}
    >
      {/* Card header */}
      <div
        className={cn(
          'p-4 border-b border-outline-variant flex justify-between items-start',
          !req.live && 'bg-surface-container-lowest',
        )}
      >
        <div>
          <p className="label-mono text-on-surface-variant mb-1">{req.code}</p>
          <h2
            className={cn(
              'font-display text-headline-md',
              req.live ? 'text-on-surface' : 'text-on-surface-variant',
            )}
          >
            {req.title}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCopyInterviewUrl}
            className={cn(
              'size-8 border border-outline-variant flex items-center justify-center transition-colors duration-150',
              copied
                ? 'bg-surface-container text-primary-fixed-dim'
                : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface',
            )}
            title={copied ? 'Interview URL copied' : `Copy interview URL: ${interviewUrl}`}
            aria-label={copied ? 'Interview URL copied' : 'Copy interview URL'}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button
            onClick={handleToggle}
            className={cn(
              'px-3 py-1 label-mono flex items-center gap-2 select-none transition-colors duration-200',
              req.live
                ? 'bg-primary-container text-on-primary-container'
                : 'bg-surface-container-lowest text-on-surface-variant border border-outline-variant',
            )}
          >
            <span
              className={cn(
                'size-2',
                req.live ? 'bg-[var(--emerald-chip-text)] blink' : 'bg-outline',
              )}
            />
            {req.live ? 'LIVE' : 'OFFLINE'}
          </button>
        </div>
      </div>

      {/* Card body — metadata grid */}
      <div
        className={cn(
          'p-4 border-b border-outline-variant flex-1',
          !req.live && 'bg-surface-container-lowest',
        )}
      >
        <div className={cn('grid grid-cols-2 gap-4', !req.live && 'opacity-70')}>
          <div>
            <p className="label-mono text-on-surface-variant mb-1">Domain</p>
            <p className={cn('text-body-md', req.live ? 'text-on-surface' : 'text-on-surface-variant')}>
              {req.domain}
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-1.5">
            {visibleRequirements.map(requirement => (
              <span
                key={requirement}
                className={cn(
                  'border border-outline-variant bg-surface-container-lowest px-2 py-1 label-mono leading-none',
                  req.live ? 'text-on-surface' : 'text-on-surface-variant',
                )}
              >
                {requirement}
              </span>
            ))}
            {hiddenRequirementCount > 0 && (
              <span
                className={cn(
                  'border border-outline-variant bg-surface-container px-2 py-1 label-mono leading-none',
                  req.live ? 'text-primary-fixed-dim' : 'text-on-surface-variant',
                )}
                aria-label={`${hiddenRequirementCount} more technical requirements`}
                title={req.technicalRequirements.slice(3).join(', ')}
              >
                +{hiddenRequirementCount}
              </span>
            )}
          </div>
          <div>
            <p className="label-mono text-on-surface-variant mb-1">Open Date</p>
            <p className={cn('text-body-md', req.live ? 'text-on-surface' : 'text-on-surface-variant')}>
              {req.openDate}
            </p>
          </div>
          <div>
            <p className="label-mono text-on-surface-variant mb-1">Close Date</p>
            <p className={cn('text-body-md', req.live ? 'text-on-surface' : 'text-on-surface-variant')}>
              {req.closeDate}
            </p>
          </div>
        </div>

      </div>

      {/* Card footer — stats */}
      <div className={cn('flex', !req.live && 'bg-surface-container-lowest')}>
        <div className="flex-1 p-4 border-r border-outline-variant flex flex-col justify-center items-center hover:bg-surface-container transition-colors duration-150 cursor-pointer">
          <span className={cn('font-display text-headline-md', req.live ? 'text-on-surface' : 'text-on-surface-variant')}>
            {req.clicks}
          </span>
          <span className="label-mono text-on-surface-variant mt-1">Clicks</span>
        </div>
        <button
          type="button"
          onClick={openCompletedInterviews}
          className="flex-1 p-4 flex flex-col justify-center items-center hover:bg-surface-container transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-container"
          aria-label={`View completed interviews for ${req.code}`}
        >
          <span className={cn('font-display text-headline-md', req.live ? 'text-primary-container' : 'text-on-surface-variant')}>
            {req.completed > 0 ? req.completed : '—'}
          </span>
          <span className="label-mono text-on-surface-variant mt-1">Completed</span>
        </button>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Requisitions Page                                                         */
/* -------------------------------------------------------------------------- */

export default function ConsoleRequisitions() {
  const { data: reqs = [], isLoading } = useConsoleRequisitions();
  const toggleMutation = useToggleRequisitionStatus();
  const [search, setSearch] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [titleFilter, setTitleFilter] = useState('');
  const [domainFilter, setDomainFilter] = useState('');
  const [requirementFilters, setRequirementFilters] = useState<string[]>([]);

  const toggleStatus = useCallback(
    (id: string) => {
      const req = reqs.find(r => r.id === id);
      if (!req) return;
      toggleMutation.mutate({ id, live: !req.live });
    },
    [reqs, toggleMutation],
  );

  const domains = useMemo(
    () => Array.from(new Set(reqs.map(req => req.domain))).sort((a, b) => a.localeCompare(b)),
    [reqs],
  );
  const jobTitles = useMemo(
    () => Array.from(new Set(reqs.map(req => req.title))).sort((a, b) => a.localeCompare(b)),
    [reqs],
  );
  const technicalRequirements = useMemo(
    () =>
      Array.from(new Set(reqs.flatMap(req => req.technicalRequirements))).sort((a, b) =>
        a.localeCompare(b),
      ),
    [reqs],
  );

  const toggleRequirementFilter = (requirement: string) => {
    setRequirementFilters(prev =>
      prev.includes(requirement)
        ? prev.filter(item => item !== requirement)
        : [...prev, requirement],
    );
  };

  const clearFilters = () => {
    setStatusFilter('all');
    setTitleFilter('');
    setDomainFilter('');
    setRequirementFilters([]);
    setRequirementsOpen(false);
  };

  const hasFilters =
    statusFilter !== 'all' ||
    titleFilter.trim().length > 0 ||
    domainFilter.trim().length > 0 ||
    requirementFilters.length > 0;

  const filtered = reqs.filter(r => {
    const searchTerm = search.trim().toLowerCase();

    const matchesSearch =
      searchTerm.length === 0 ||
      r.title.toLowerCase().includes(searchTerm) ||
      r.code.toLowerCase().includes(searchTerm) ||
      r.domain.toLowerCase().includes(searchTerm) ||
      r.technicalRequirements.some(requirement =>
        requirement.toLowerCase().includes(searchTerm),
      );
    const matchesStatus =
      statusFilter === 'all' ||
      (statusFilter === 'live' && r.live) ||
      (statusFilter === 'offline' && !r.live);
    const matchesTitle = titleFilter.length === 0 || r.title === titleFilter;
    const matchesDomain = domainFilter.length === 0 || r.domain === domainFilter;
    const matchesRequirements =
      requirementFilters.length === 0 ||
      requirementFilters.every(requirement =>
        r.technicalRequirements.includes(requirement),
      );

    return matchesSearch && matchesStatus && matchesTitle && matchesDomain && matchesRequirements;
  });

  const liveCount = reqs.filter(r => r.live).length;

  return (
    <ConsoleLayout>
      {/* Control bar */}
      <header className="h-16 border-b border-outline-variant bg-surface flex items-center justify-between px-4 sticky top-0 z-30">
        <div className="flex items-center gap-4 h-full">
          {/* Search */}
          <div className="relative h-10 w-64 flex items-center border border-outline-variant bg-surface-container-lowest focus-within:border-primary-container transition-colors">
            <Search size={16} className="absolute left-3 text-on-surface-variant" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="SEARCH REQUISITIONS..."
              className="w-full h-full bg-transparent border-none text-on-surface font-mono text-xs uppercase tracking-[0.15em] pl-10 pr-3 focus:outline-none focus:ring-0 placeholder:text-on-surface-variant"
            />
          </div>
          {/* Filters */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setFiltersOpen(open => !open)}
              className={cn(
                'h-10 px-4 border label-mono flex items-center gap-2 transition-colors duration-150',
                filtersOpen || hasFilters
                  ? 'border-primary-container bg-surface-container text-on-surface'
                  : 'border-outline-variant text-on-surface-variant hover:bg-surface-container hover:text-on-surface',
              )}
              aria-expanded={filtersOpen}
            >
              <SlidersHorizontal size={16} />
              Filters
              {hasFilters && (
                <span className="bg-primary-container text-on-primary-container px-1.5 py-0.5 leading-none">
                  {
                    [
                      statusFilter !== 'all',
                      titleFilter.trim().length > 0,
                      domainFilter.trim().length > 0,
                      requirementFilters.length > 0,
                    ].filter(Boolean).length
                  }
                </span>
              )}
            </button>

            {filtersOpen && (
              <div className="absolute left-0 top-12 z-40 w-[520px] max-w-[calc(100vw-2rem)] border border-outline-variant bg-surface shadow-2xl">
                <div className="p-4 border-b border-outline-variant flex items-center justify-between gap-3">
                  <p className="label-mono text-on-surface">Filter Requisitions</p>
                  <button
                    type="button"
                    onClick={clearFilters}
                    className="label-mono text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-150"
                  >
                    Clear
                  </button>
                </div>

                <div className="p-4 space-y-4">
                  <div>
                    <p className="label-mono text-on-surface-variant mb-2">Status</p>
                    <div className="grid grid-cols-3 gap-px border border-outline-variant bg-outline-variant">
                      {(['all', 'live', 'offline'] as const).map(status => (
                        <button
                          key={status}
                          type="button"
                          onClick={() => setStatusFilter(status)}
                          className={cn(
                            'h-9 bg-surface label-mono transition-colors duration-150',
                            statusFilter === status
                              ? 'text-on-primary-container bg-primary-container'
                              : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface',
                          )}
                        >
                          {status === 'all' ? 'All' : status === 'live' ? 'Live' : 'Offline'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <label className="block">
                      <span className="label-mono text-on-surface-variant mb-2 block">Job Title</span>
                      <select
                        value={titleFilter}
                        onChange={e => setTitleFilter(e.target.value)}
                        className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs uppercase tracking-[0.12em] focus:outline-none focus:border-primary-container placeholder:text-on-surface-variant"
                      >
                        <option value="">All Job Titles</option>
                        {jobTitles.map(title => (
                          <option key={title} value={title}>
                            {title}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="block">
                      <span className="label-mono text-on-surface-variant mb-2 block">Domain</span>
                      <select
                        value={domainFilter}
                        onChange={e => setDomainFilter(e.target.value)}
                        className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 text-on-surface font-mono text-xs uppercase tracking-[0.12em] focus:outline-none focus:border-primary-container placeholder:text-on-surface-variant"
                      >
                        <option value="">All Domains</option>
                        {domains.map(domain => (
                          <option key={domain} value={domain}>
                            {domain}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div>
                    <p className="label-mono text-on-surface-variant mb-2">Technical Requirements</p>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setRequirementsOpen(open => !open)}
                        className={cn(
                          'min-h-10 w-full border px-3 py-2 text-left label-mono transition-colors duration-150',
                          requirementsOpen || requirementFilters.length > 0
                            ? 'border-primary-container bg-surface-container text-on-surface'
                            : 'border-outline-variant bg-surface-container-lowest text-on-surface-variant hover:text-on-surface',
                        )}
                        aria-expanded={requirementsOpen}
                      >
                        {requirementFilters.length > 0
                          ? requirementFilters.join(', ')
                          : 'Select Requirements'}
                      </button>

                      {requirementsOpen && (
                        <div className="absolute left-0 top-12 z-50 max-h-64 w-full overflow-y-auto border border-outline-variant bg-surface shadow-2xl">
                          {technicalRequirements.map(requirement => {
                            const active = requirementFilters.includes(requirement);

                            return (
                              <label
                                key={requirement}
                                className="flex min-h-10 cursor-pointer items-center gap-3 border-b border-outline-variant px-3 last:border-b-0 hover:bg-surface-container"
                              >
                                <input
                                  type="checkbox"
                                  checked={active}
                                  onChange={() => toggleRequirementFilter(requirement)}
                                  className="size-4 accent-[var(--primary-container)]"
                                />
                                <span className={cn('label-mono', active ? 'text-on-surface' : 'text-on-surface-variant')}>
                                  {requirement}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
        <Link
          to="/console/requisitions/new"
          className="h-10 px-6 bg-primary-container text-on-primary-container label-mono font-bold flex items-center gap-2 border border-primary-container hover:bg-transparent hover:text-primary-fixed-dim transition-colors duration-150"
        >
          <Plus size={16} />
          New Requisition
        </Link>
      </header>

      {/* Content */}
      <div className="p-4 flex-1">
        {/* Title row */}
        <div className="mb-4 flex items-baseline gap-4">
          <h1 className="font-display text-headline-lg text-on-surface tracking-tight">
            Active Requisitions
          </h1>
          <span className="label-mono text-on-surface-variant">
            {filtered.length} total · {liveCount} live
          </span>
        </div>

        {/* Interlocking grid. Filler cells cover the container's gutter-color
            background in incomplete last rows, per breakpoint column count. */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-px bg-outline-variant border border-outline-variant">
          {filtered.map(req => (
            <ReqCard key={req.id} req={req} onToggle={toggleStatus} />
          ))}
          {Array.from({ length: (2 - (filtered.length % 2)) % 2 }).map((_, i) => (
            <div key={`md-fill-${i}`} className="hidden md:block xl:hidden bg-surface-container-lowest" />
          ))}
          {Array.from({ length: (4 - (filtered.length % 4)) % 4 }).map((_, i) => (
            <div key={`xl-fill-${i}`} className="hidden xl:block bg-surface-container-lowest" />
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="py-16 flex flex-col items-center gap-2">
            <p className="label-mono text-on-surface-variant">
              {isLoading ? 'Loading requisitions…' : 'No requisitions match your search.'}
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="py-8 px-8 flex flex-col md:flex-row justify-between items-center gap-4 border-t border-outline-variant bg-surface-container-lowest mt-auto">
        <p className="font-display text-headline-md font-bold text-primary-fixed-dim">KANDIDLY AI</p>
        <div className="flex gap-6">
          {['Privacy', 'Terms', 'Security', 'Status'].map(label => (
            <a key={label} href="#" className="label-mono text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-200">
              {label}
            </a>
          ))}
        </div>
        <p className="label-mono text-on-surface-variant">© 2026 Kandidly AI. All systems nominal.</p>
      </footer>
    </ConsoleLayout>
  );
}
