/**
 * /admin — System overview: pipeline metrics + recent interviews.
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueries } from '@tanstack/react-query';
import { CheckCircle2, BarChart3, Briefcase, Activity, Filter, ArrowRight } from 'lucide-react';
import { adminApi } from '../../lib/api';
import { cn } from '../../lib/utils';
import { Skeleton, ErrorState, EmptyState } from '../../components/ui';
import type { FunnelOut, RequisitionOut, AdminApplicationListOut } from '../../lib/types';

const PAGE_SIZE = 6;
const COMPLETED_STATES = new Set(['completed', 'scored', 'reviewed']);

type RecentApplication = AdminApplicationListOut & { requisitionTitle: string };

function fmtDate(iso: string): string {
  return new Date(iso)
    .toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
    .toUpperCase();
}

// Report scores are stored as a 1-5 weighted average (SPEC rubric scale);
// displayed here projected onto a 0-100 index for at-a-glance reading.
function toScoreIndex(score: number | null): number | null {
  return score != null ? Math.round(score * 20) : null;
}

export default function AdminDashboard() {
  const { data: funnel, isLoading: funnelLoading, isError: funnelError } = useQuery<FunnelOut>({
    queryKey: ['funnel'],
    queryFn: adminApi.getFunnel,
  });

  const { data: reqs, isLoading: reqsLoading, isError: reqsError } = useQuery<RequisitionOut[]>({
    queryKey: ['requisitions'],
    queryFn: adminApi.getRequisitions,
  });

  const appQueries = useQueries({
    queries: (reqs ?? []).map(r => ({
      queryKey: ['requisitions', r.id, 'applications'],
      queryFn: () => adminApi.getApplications(r.id),
    })),
  });

  const overviewLoading = funnelLoading || reqsLoading || appQueries.some(q => q.isLoading);
  const overviewError = funnelError || reqsError || appQueries.some(q => q.isError);

  const recent = useMemo<RecentApplication[]>(() => {
    if (!reqs) return [];
    const titleById = new Map(reqs.map(r => [r.id, r.title]));
    const all = appQueries.flatMap((q, i) => {
      const reqId = reqs[i]?.id;
      return (q.data ?? []).map(app => ({ ...app, requisitionTitle: titleById.get(reqId!) ?? '—' }));
    });
    return all.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [appQueries, reqs]);

  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const stages = funnel?.stages ?? [];
  const totalPipeline = stages.reduce((s, r) => s + r.count, 0);
  const completed = stages
    .filter(s => COMPLETED_STATES.has(s.state))
    .reduce((s, r) => s + r.count, 0);
  const completedPct = totalPipeline > 0 ? Math.round((completed / totalPipeline) * 100) : 0;
  const inInterview = stages.find(s => s.state === 'in_interview')?.count ?? 0;
  const maxStageCount = Math.max(1, ...stages.map(s => s.count));

  const openReqs = reqs?.filter(r => r.status === 'open').length ?? 0;
  const totalReqs = reqs?.length ?? 0;

  const scored = recent.filter(a => a.overall_score != null);
  const avgScoreIndex = scored.length > 0
    ? Math.round((scored.reduce((s, a) => s + (a.overall_score ?? 0), 0) / scored.length) * 20)
    : null;

  const today = new Date()
    .toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
    .toUpperCase();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-headline-lg text-on-surface">System Overview</h1>
          <p className="label-mono text-on-surface-variant mt-1">Real-time telemetry / {today}</p>
        </div>
        <div className="flex items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-on-surface shrink-0">
          <span className="size-2 bg-primary-container blink" />
          Live
        </div>
      </div>

      {/* Metric tiles */}
      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-px bg-outline-variant border border-outline-variant">
        {overviewLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[190px]" />)
        ) : (
          <>
            <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
              <div className="flex justify-between items-start">
                <span className="label-mono text-on-surface-variant">Completed interviews</span>
                <CheckCircle2 size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
              </div>
              <p className="font-display text-[44px] font-bold tracking-tight leading-none text-primary-fixed-dim tabular">
                {completed.toLocaleString()}
              </p>
              <p className="label-mono text-on-surface-variant">{completedPct}% of total pipeline</p>
            </div>

            <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
              <div className="flex justify-between items-start">
                <span className="label-mono text-on-surface-variant">Average score</span>
                <BarChart3 size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
              </div>
              <p className="font-display text-[44px] font-bold tracking-tight leading-none text-on-surface tabular">
                {avgScoreIndex ?? '—'}
              </p>
              <div className="w-full h-1 bg-surface-container-highest">
                <div className="h-full bg-primary-container" style={{ width: `${avgScoreIndex ?? 0}%` }} />
              </div>
            </div>

            <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
              <div className="flex justify-between items-start">
                <span className="label-mono text-on-surface-variant">Active requisitions</span>
                <Briefcase size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
              </div>
              <p className="font-display text-[44px] font-bold tracking-tight leading-none text-on-surface tabular">
                {openReqs}
              </p>
              <p className="label-mono text-on-surface-variant">{totalReqs} total requisitions</p>
            </div>

            <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
              <div className="flex justify-between items-start">
                <span className="label-mono text-on-surface-variant">In progress</span>
                <Activity size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
              </div>
              <p className="font-display text-[44px] font-bold tracking-tight leading-none text-on-surface tabular">
                {inInterview}
              </p>
              <div className="flex items-end gap-px h-10">
                {stages.length === 0 ? (
                  <div className="flex-1 bg-surface-container-highest h-[20%]" />
                ) : (
                  stages.map((s, i) => (
                    <div
                      key={s.state}
                      className={cn('flex-1', i >= stages.length - 2 ? 'bg-primary-container' : 'bg-surface-container-highest')}
                      style={{ height: `${Math.max(10, (s.count / maxStageCount) * 100)}%` }}
                    />
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </section>

      {/* Recent interviews */}
      <section className="border border-outline-variant">
        <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
          <h2 className="label-mono text-on-surface">// RECENT_INTERVIEWS</h2>
          <button className="flex items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-on-surface hover:border-primary-container hover:text-primary-fixed-dim transition-colors duration-150">
            <Filter size={14} />
            Filter
          </button>
        </div>

        {overviewError ? (
          <ErrorState title="Couldn't load recent interviews" />
        ) : overviewLoading ? (
          <div className="p-5 space-y-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-10" />)}
          </div>
        ) : recent.length === 0 ? (
          <EmptyState
            icon={<Briefcase size={20} />}
            title="No applications yet"
            description="Create a requisition and share the invite link to start."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse font-mono text-label-sm">
                <thead>
                  <tr className="bg-surface-container-lowest border-b border-outline-variant">
                    <th className="label-mono p-3 text-on-surface-variant">Candidate</th>
                    <th className="label-mono p-3 text-on-surface-variant">Requisition</th>
                    <th className="label-mono p-3 text-on-surface-variant">Score</th>
                    <th className="label-mono p-3 text-on-surface-variant">Submitted</th>
                    <th className="label-mono p-3 text-on-surface-variant text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="bg-surface">
                  {recent.slice(0, visibleCount).map(app => {
                    const scoreIndex = toScoreIndex(app.overall_score);
                    const strong = scoreIndex != null && scoreIndex >= 80;
                    return (
                      <tr key={app.id} className="border-b border-outline-variant last:border-b-0 hover:bg-surface-container transition-colors duration-150">
                        <td className="p-3 text-on-surface">{app.candidate_name}</td>
                        <td className="p-3 text-on-surface-variant">{app.requisitionTitle}</td>
                        <td className="p-3">
                          {scoreIndex != null ? (
                            <span
                              className={cn(
                                'inline-block border px-2 py-0.5 bg-surface-container-lowest whitespace-nowrap',
                                strong ? 'border-primary-container text-primary-fixed-dim' : 'border-outline-variant text-on-surface'
                              )}
                            >
                              {scoreIndex} / 100
                            </span>
                          ) : (
                            <span className="text-on-surface-variant">—</span>
                          )}
                        </td>
                        <td className="p-3 text-on-surface-variant">{fmtDate(app.created_at)}</td>
                        <td className="p-3 text-right">
                          <Link to={`/admin/applications/${app.id}`}>
                            <ArrowRight size={16} className="inline-block text-text-muted hover:text-primary-fixed-dim transition-colors duration-150" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {visibleCount < recent.length && (
              <div className="p-3 bg-surface-container-lowest border-t border-outline-variant flex justify-center">
                <button
                  onClick={() => setVisibleCount(c => c + PAGE_SIZE)}
                  className="label-mono text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-150"
                >
                  Load more records
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
