/**
 * /console — Voice Console dashboard: system overview with metric tiles,
 * recent interviews table, and trend charts.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  BarChart3,
  Briefcase,
  Activity,
  Filter,
  ArrowRight,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import ConsoleLayout from './ConsoleLayout';
import { formatDuration, toLedgerRow, useConsoleDashboard } from '../../lib/consoleApi';

const MINI_BAR_HEIGHTS = [35, 55, 45, 70, 85, 60, 42];

const PAGE_SIZE = 6;

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

/* -------------------------------------------------------------------------- */
/*  SVG Charts                                                                */
/* -------------------------------------------------------------------------- */

function BarChartSVG({ data, labels }: { data: number[]; labels: string[] }) {
  const max = Math.max(...data, 1);
  const chartH = 160;
  const chartW = 480;
  const barW = chartW / data.length - 6;
  const yTicks = [0, 25, 50, 75, 100];

  return (
    <svg viewBox={`0 0 ${chartW + 40} ${chartH + 30}`} className="w-full h-auto">
      {/* Y-axis labels */}
      {yTicks.map(t => {
        const y = chartH - (t / 100) * chartH;
        return (
          <text
            key={t}
            x={0}
            y={y + 4}
            className="fill-on-surface-variant"
            fontSize={9}
            fontFamily="'JetBrains Mono', monospace"
            textAnchor="end"
            dominantBaseline="middle"
          >
            {t}
          </text>
        );
      })}
      {/* Grid lines */}
      {yTicks.map(t => {
        const y = chartH - (t / 100) * chartH;
        return <line key={t} x1={8} y1={y} x2={chartW + 40} y2={y} stroke="#434656" strokeWidth={0.5} />;
      })}
      {/* Bars */}
      {data.map((v, i) => {
        const h = (v / max) * chartH;
        const x = 14 + i * ((chartW - 8) / data.length);
        return (
          <g key={i}>
            <rect
              x={x}
              y={chartH - h}
              width={barW}
              height={h}
              fill="#2e5bff"
              className="opacity-80 hover:opacity-100 transition-opacity"
            />
            <text
              x={x + barW / 2}
              y={chartH + 16}
              textAnchor="middle"
              className="fill-on-surface-variant"
              fontSize={9}
              fontFamily="'JetBrains Mono', monospace"
            >
              {labels[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function AreaChartSVG({ data, labels }: { data: number[]; labels: string[] }) {
  const max = Math.max(...data, 1);
  const chartH = 160;
  const chartW = 480;
  const yTicks = [0, 5, 10, 15, 20];
  const step = (chartW - 20) / (data.length - 1);

  const points = data.map((v, i) => ({
    x: 14 + i * step,
    y: chartH - (v / max) * chartH * 0.9,
  }));
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const areaPath = `${linePath} L${points[points.length - 1].x},${chartH} L${points[0].x},${chartH} Z`;

  return (
    <svg viewBox={`0 0 ${chartW + 40} ${chartH + 30}`} className="w-full h-auto">
      {/* Y-axis labels */}
      {yTicks.map(t => {
        const y = chartH - (t / max) * chartH * 0.9;
        return (
          <text
            key={t}
            x={0}
            y={y + 4}
            className="fill-on-surface-variant"
            fontSize={9}
            fontFamily="'JetBrains Mono', monospace"
            textAnchor="end"
            dominantBaseline="middle"
          >
            {t}
          </text>
        );
      })}
      {/* Grid lines */}
      {yTicks.map(t => {
        const y = chartH - (t / max) * chartH * 0.9;
        return <line key={t} x1={8} y1={y} x2={chartW + 40} y2={y} stroke="#434656" strokeWidth={0.5} />;
      })}
      {/* Area fill */}
      <path d={areaPath} fill="#ffb4ab" opacity={0.12} />
      {/* Line */}
      <path d={linePath} fill="none" stroke="#ffb4ab" strokeWidth={2} />
      {/* Data dots */}
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="#ffb4ab" />
      ))}
      {/* X-axis labels */}
      {points.map((p, i) => (
        <text
          key={i}
          x={p.x}
          y={chartH + 16}
          textAnchor="middle"
          className="fill-on-surface-variant"
          fontSize={9}
          fontFamily="'JetBrains Mono', monospace"
        >
          {labels[i]}
        </text>
      ))}
    </svg>
  );
}




/* -------------------------------------------------------------------------- */
/*  Dashboard                                                                 */
/* -------------------------------------------------------------------------- */

export default function ConsoleDashboard() {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [now, setNow] = useState(() => new Date());
  const { data: dashboard } = useConsoleDashboard();

  const weekLabels = Array.from({ length: 12 }, (_, i) => `W${i + 1}`);
  const weeklyCompleted = dashboard?.weekly_completed.map(p => p.count) ?? Array(12).fill(0);
  const weeklyDropped = dashboard?.weekly_dropped.map(p => p.count) ?? Array(12).fill(0);
  const recentInterviews = (dashboard?.recent_interviews ?? []).map(toLedgerRow);
  const averageScore = dashboard?.average_score ?? null;

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(new Date());
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <ConsoleLayout>
      <div className="p-8 space-y-8 max-w-[1280px]">
        {/* Header */}
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="font-display text-headline-lg text-on-surface">System Overview</h1>
            <p className="label-mono text-on-surface-variant mt-1">
              Real-time telemetry / {dateTimeFormatter.format(now)}
            </p>
          </div>
          <div className="flex items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-on-surface shrink-0">
            <span className="size-2 bg-[var(--emerald-chip-text)] blink" />
            Live
          </div>
        </div>

        {/* Metric tiles */}
        <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-px bg-outline-variant border border-outline-variant">
          {/* Completed Interviews */}
          <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
            <div className="flex justify-between items-start">
              <span className="label-mono text-on-surface-variant">Completed interviews</span>
              <CheckCircle2 size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
            </div>
            <p className="font-display text-[44px] font-bold tracking-tight leading-none text-primary-fixed-dim tabular">
              {(dashboard?.completed_total ?? 0).toLocaleString()}
            </p>
            <p className="label-mono text-primary-fixed-dim">
              {dashboard?.completed_delta_pct != null
                ? `${dashboard.completed_delta_pct >= 0 ? '+' : ''}${dashboard.completed_delta_pct}% vs last week`
                : 'No prior-week data'}
            </p>
          </div>

          {/* Average Score */}
          <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
            <div className="flex justify-between items-start">
              <span className="label-mono text-on-surface-variant">Average score</span>
              <BarChart3 size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
            </div>
            <p className="font-display text-[44px] font-bold tracking-tight leading-none text-on-surface tabular">
              {averageScore != null ? averageScore : '—'}
            </p>
            <div className="w-full h-1 bg-surface-container-highest">
              <div
                className="h-full bg-primary-container"
                style={{ width: `${Math.min(100, averageScore ?? 0)}%` }}
              />
            </div>
          </div>

          {/* Active Requisitions */}
          <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
            <div className="flex justify-between items-start">
              <span className="label-mono text-on-surface-variant">Active requisitions</span>
              <Briefcase size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
            </div>
            <p className="font-display text-[44px] font-bold tracking-tight leading-none text-on-surface tabular">
              {dashboard?.active_requisitions ?? 0}
            </p>
            <p className="label-mono text-on-surface-variant">
              Across {dashboard?.domain_count ?? 0} domains
            </p>
          </div>

          {/* System Load */}
          <div className="group bg-surface h-[190px] p-5 flex flex-col justify-between hover:bg-surface-container-low transition-colors duration-150">
            <div className="flex justify-between items-start">
              <span className="label-mono text-on-surface-variant">System load</span>
              <Activity size={20} className="text-text-muted group-hover:text-primary-fixed-dim transition-colors duration-150" />
            </div>
            <p className="font-display text-[44px] font-bold tracking-tight leading-none text-on-surface tabular">
              42%
            </p>
            <div className="flex items-end gap-px h-10">
              {MINI_BAR_HEIGHTS.map((h, i) => (
                <div
                  key={i}
                  className={cn('flex-1', i >= MINI_BAR_HEIGHTS.length - 2 ? 'bg-primary-container' : 'bg-surface-container-highest')}
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
          </div>
        </section>

        {/* Recent interviews */}
        <section className="border border-outline-variant">
          <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
            <h2 className="label-mono text-on-surface">// Recent_Interviews</h2>
            <button className="flex items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-on-surface hover:border-primary-container hover:text-primary-fixed-dim transition-colors duration-150">
              <Filter size={14} />
              Filter
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse font-mono text-label-sm">
              <thead>
                <tr className="bg-surface-container-lowest border-b border-outline-variant">
                  <th className="label-mono p-3 text-on-surface-variant">Candidate ID</th>
                  <th className="label-mono p-3 text-on-surface-variant">Requisition</th>
                  <th className="label-mono p-3 text-on-surface-variant">Score</th>
                  <th className="label-mono p-3 text-on-surface-variant">Duration</th>
                  <th className="label-mono p-3 text-on-surface-variant text-right">Action</th>
                </tr>
              </thead>
              <tbody className="bg-surface">
                {recentInterviews.slice(0, visibleCount).map(row => {
                  const strong = (row.finalScore ?? 0) >= 80;
                  return (
                    <tr key={row.id} className="border-b border-outline-variant last:border-b-0 hover:bg-surface-container transition-colors duration-150">
                      <td className="p-3 text-on-surface">{row.code} · {row.candidateName}</td>
                      <td className="p-3 text-on-surface-variant">{row.requisitionId}</td>
                      <td className="p-3">
                        <span
                          className={cn(
                            'inline-block border px-2 py-0.5 bg-surface-container-lowest whitespace-nowrap',
                            strong ? 'border-primary-container text-primary-fixed-dim' : 'border-outline-variant text-on-surface'
                          )}
                        >
                          {row.finalScore != null ? `${Math.round(row.finalScore)} / 100` : 'Evaluating'}
                        </span>
                      </td>
                      <td className="p-3 text-on-surface-variant">{formatDuration(row.durationSeconds)}</td>
                      <td className="p-3 text-right">
                        <Link to={`/console/interviews/${row.id}`}>
                          <ArrowRight size={16} className="inline-block text-text-muted hover:text-primary-fixed-dim transition-colors duration-150" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {visibleCount < recentInterviews.length && (
            <div className="p-3 bg-surface-container-lowest border-t border-outline-variant flex justify-center">
              <button
                onClick={() => setVisibleCount(c => c + PAGE_SIZE)}
                className="label-mono text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-150"
              >
                Load more records
              </button>
            </div>
          )}
        </section>

        {/* Charts */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-outline-variant border border-outline-variant">
          {/* Interviews Completed Over Time */}
          <div className="bg-surface p-5 space-y-4">
            <h3 className="label-mono text-on-surface-variant">// Interviews_Completed_Over_Time</h3>
            <BarChartSVG data={weeklyCompleted} labels={weekLabels} />
          </div>

          {/* Interviews Dropped Midway */}
          <div className="bg-surface p-5 space-y-4">
            <h3 className="label-mono text-on-surface-variant">// Interviews_Dropped_Midway</h3>
            <AreaChartSVG data={weeklyDropped} labels={weekLabels} />
          </div>
        </section>
      </div>
    </ConsoleLayout>
  );
}
