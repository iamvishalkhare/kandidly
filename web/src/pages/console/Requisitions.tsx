/**
 * /console/requisitions — Requisition management grid.
 * Interlocking card grid with LIVE/OFFLINE toggles, search, and filters.
 */

import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Search, SlidersHorizontal, Plus } from 'lucide-react';
import { cn } from '../../lib/utils';
import ConsoleLayout from './ConsoleLayout';

/* -------------------------------------------------------------------------- */
/*  Mock data                                                                 */
/* -------------------------------------------------------------------------- */

interface Requisition {
  id: string;
  code: string;
  title: string;
  domain: string;
  location: string;
  openDate: string;
  closeDate: string;
  clicks: number;
  completed: number;
  live: boolean;
}

const MOCK_REQUISITIONS: Requisition[] = [
  {
    id: 'req-1', code: 'ENG-001', title: 'Senior AI Engineer',
    domain: 'Machine Learning', location: 'Remote / NYC',
    openDate: '24/05/2026', closeDate: '15/07/2026',
    clicks: 142, completed: 12, live: true,
  },
  {
    id: 'req-2', code: 'DES-042', title: 'Product Designer',
    domain: 'Product', location: 'London',
    openDate: '28/05/2026', closeDate: 'N/A',
    clicks: 89, completed: 4, live: true,
  },
  {
    id: 'req-3', code: 'MKT-011', title: 'Growth Manager',
    domain: 'Marketing', location: 'San Francisco',
    openDate: '10/04/2026', closeDate: '01/06/2026',
    clicks: 210, completed: 0, live: false,
  },
  {
    id: 'req-4', code: 'ENG-017', title: 'Frontend Engineer',
    domain: 'Engineering', location: 'Remote / Berlin',
    openDate: '02/06/2026', closeDate: 'N/A',
    clicks: 67, completed: 8, live: true,
  },
  {
    id: 'req-5', code: 'DAT-003', title: 'Data Scientist',
    domain: 'Data Science', location: 'Remote / Singapore',
    openDate: '15/05/2026', closeDate: '30/07/2026',
    clicks: 195, completed: 15, live: true,
  },
  {
    id: 'req-6', code: 'OPS-008', title: 'DevOps Lead',
    domain: 'Infrastructure', location: 'Austin, TX',
    openDate: '01/03/2026', closeDate: '15/05/2026',
    clicks: 312, completed: 0, live: false,
  },
  {
    id: 'req-7', code: 'ENG-023', title: 'Backend Engineer',
    domain: 'Engineering', location: 'Remote',
    openDate: '18/06/2026', closeDate: 'N/A',
    clicks: 34, completed: 2, live: true,
  },
  {
    id: 'req-8', code: 'PM-005', title: 'Product Manager',
    domain: 'Product', location: 'NYC',
    openDate: '20/06/2026', closeDate: 'N/A',
    clicks: 51, completed: 3, live: true,
  },
];

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
  const [flash, setFlash] = useState(false);

  const handleToggle = () => {
    setFlash(true);
    onToggle(req.id);
    // Remove flash class after animation completes
    setTimeout(() => setFlash(false), 300);
  };

  return (
    <div
      className={cn(
        'bg-surface flex flex-col transition-all duration-200',
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
          <div>
            <p className="label-mono text-on-surface-variant mb-1">Location</p>
            <p className={cn('text-body-md', req.live ? 'text-on-surface' : 'text-on-surface-variant')}>
              {req.location}
            </p>
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
        <div className="flex-1 p-4 flex flex-col justify-center items-center hover:bg-surface-container transition-colors duration-150 cursor-pointer">
          <span className={cn('font-display text-headline-md', req.live ? 'text-primary-container' : 'text-on-surface-variant')}>
            {req.completed > 0 ? req.completed : '—'}
          </span>
          <span className="label-mono text-on-surface-variant mt-1">Completed</span>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Requisitions Page                                                         */
/* -------------------------------------------------------------------------- */

export default function ConsoleRequisitions() {
  const [reqs, setReqs] = useState<Requisition[]>(MOCK_REQUISITIONS);
  const [search, setSearch] = useState('');

  const toggleStatus = useCallback((id: string) => {
    setReqs(prev =>
      prev.map(r => (r.id === id ? { ...r, live: !r.live } : r)),
    );
  }, []);

  const filtered = search.trim()
    ? reqs.filter(
        r =>
          r.title.toLowerCase().includes(search.toLowerCase()) ||
          r.code.toLowerCase().includes(search.toLowerCase()) ||
          r.domain.toLowerCase().includes(search.toLowerCase()),
      )
    : reqs;

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
          <button className="h-10 px-4 border border-outline-variant text-on-surface-variant label-mono flex items-center gap-2 hover:bg-surface-container hover:text-on-surface transition-colors duration-150">
            <SlidersHorizontal size={16} />
            Filters
          </button>
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
            <p className="label-mono text-on-surface-variant">No requisitions match your search.</p>
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
