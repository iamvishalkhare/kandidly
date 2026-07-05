/**
 * /admin/applications/:id — Application detail with tabs:
 * Overview (state timeline), Form answers, Transcript, Report.
 */

import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, MessageSquare, FileText, BarChart2,
} from 'lucide-react';
import { adminApi } from '../../lib/api';
import {
  PageHeader, Card, Tabs, StateBadge, Skeleton, ErrorState, EmptyState,
  Button, Select, Textarea, Badge, useToast,
} from '../../components/ui';
import { cn } from '../../lib/utils';
import type {
  AdminApplicationDetailOut, TranscriptOut, ReportOut, TurnOut,
} from '../../lib/types';

const APPLICATION_STATES_ORDERED = [
  'registered', 'form_in_progress', 'form_submitted', 'plan_ready',
  'in_lobby', 'in_interview', 'completed', 'scored', 'reviewed',
];

// ─── Overview tab ─────────────────────────────────────────────────────────────

function OverviewTab({ app }: { app: AdminApplicationDetailOut }) {
  const ts = app.state_timestamps ?? {};

  return (
    <div className="space-y-6">
      {/* Summary row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Candidate</p>
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{app.candidate_name}</p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{app.candidate_email}</p>
        </div>
        <div>
          <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Current state</p>
          <StateBadge state={app.state} />
        </div>
        {app.overall_score != null && (
          <div>
            <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Overall score</p>
            <p
              className="text-2xl font-semibold tabular"
              style={{ color: app.overall_score >= 4 ? '#34d399' : app.overall_score >= 3 ? '#fbbf24' : '#f87171' }}
            >
              {app.overall_score.toFixed(1)} / 5
            </p>
          </div>
        )}
      </div>

      {/* Timeline */}
      <Card>
        <h3 className="text-sm font-medium mb-5" style={{ color: 'var(--text-primary)' }}>State timeline</h3>
        <div className="space-y-0">
          {APPLICATION_STATES_ORDERED.map((state, i) => {
            const time = ts[state];
            const reached = !!time;
            const isLast = i === APPLICATION_STATES_ORDERED.length - 1;
            return (
              <div key={state} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div
                    className={cn(
                      'size-3 rounded-full border-2 mt-0.5 shrink-0',
                      reached
                        ? 'border-[var(--accent)] bg-[var(--accent)]'
                        : 'border-[var(--border)] bg-transparent'
                    )}
                  />
                  {!isLast && (
                    <div
                      className="w-px flex-1 mt-0.5"
                      style={{ background: reached ? 'var(--accent)' : 'var(--border)', minHeight: '16px' }}
                    />
                  )}
                </div>
                <div className="pb-4">
                  <StateBadge state={state} />
                  {time && (
                    <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                      {new Date(time).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

// ─── Form answers tab ─────────────────────────────────────────────────────────

function AnswersTab({ app }: { app: AdminApplicationDetailOut }) {
  const answers = app.form_answers;
  if (!answers || Object.keys(answers).length === 0) {
    return (
      <EmptyState
        icon={<FileText size={20} />}
        title="No form answers"
        description="The candidate hasn't submitted the form yet."
      />
    );
  }

  return (
    <Card>
      <dl className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {Object.entries(answers).map(([key, val]) => (
          <div key={key} className="py-3 first:pt-0 last:pb-0">
            <dt
              className="text-xs font-medium uppercase tracking-wide mb-1"
              style={{ color: 'var(--text-muted)' }}
            >
              {key.replace(/_/g, ' ')}
            </dt>
            <dd className="text-sm" style={{ color: 'var(--text-primary)' }}>
              {Array.isArray(val)
                ? (val as string[]).join(', ')
                : typeof val === 'boolean'
                ? val ? 'Yes' : 'No'
                : String(val ?? '—')}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

// ─── Transcript tab ───────────────────────────────────────────────────────────

function TranscriptBubble({ turn }: { turn: TurnOut }) {
  if (turn.speaker === 'system') {
    return (
      <div className="flex justify-center">
        <span
          className="text-xs px-3 py-1 rounded-full border"
          style={{ borderColor: 'var(--border)', color: 'var(--text-muted)', background: 'var(--background)' }}
        >
          {turn.text}
        </span>
      </div>
    );
  }

  const isKandidly = turn.speaker === 'kandidly';

  return (
    <div className={cn('flex', isKandidly ? 'justify-start' : 'justify-end')}>
      <div
        className="max-w-[75%] rounded-xl px-4 py-2.5 text-sm"
        style={
          isKandidly
            ? { background: 'rgba(139,124,246,0.1)', color: 'var(--text-primary)', border: '1px solid rgba(139,124,246,0.2)' }
            : { background: 'var(--surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }
        }
      >
        <p className="text-xs font-medium mb-1 capitalize" style={{ color: 'var(--text-muted)' }}>
          {turn.speaker}
        </p>
        <p className="leading-relaxed">{turn.text}</p>
      </div>
    </div>
  );
}

function TranscriptTab({ interviewId }: { interviewId: string }) {
  const { data: transcript, isLoading, isError, refetch } = useQuery<TranscriptOut>({
    queryKey: ['transcript', interviewId],
    queryFn: () => adminApi.getTranscript(interviewId),
  });

  if (isLoading) return <Skeleton className="h-48" />;
  if (isError) return <ErrorState title="Couldn't load transcript" onRetry={refetch} />;
  if (!transcript || transcript.turns.length === 0) {
    return (
      <EmptyState
        icon={<MessageSquare size={20} />}
        title="No transcript yet"
        description="The interview hasn't started or no turns have been recorded."
      />
    );
  }

  return (
    <div className="space-y-3">
      {transcript.turns.map(turn => (
        <TranscriptBubble key={turn.id} turn={turn} />
      ))}
    </div>
  );
}

// ─── Text-interview tab (Phase-1 harness, SPEC §18.5) ────────────────────────

function ChatTab({ interviewId, appId }: { interviewId: string; appId: string }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [draft, setDraft] = useState('');
  const [lastDecision, setLastDecision] = useState<string | null>(null);
  const [ended, setEnded] = useState(false);
  const [llmMissing, setLlmMissing] = useState<string | null>(null);

  const { data: transcript, isLoading } = useQuery<TranscriptOut>({
    queryKey: ['transcript', interviewId],
    queryFn: () => adminApi.getTranscript(interviewId),
  });

  const handleError = (err: unknown) => {
    const resp = (err as { response?: { status?: number; data?: { message?: string } } }).response;
    if (resp?.status === 503) {
      setLlmMissing(resp.data?.message ?? 'LLM provider not configured.');
    } else {
      toast(resp?.data?.message ?? 'Something went wrong', 'error');
    }
  };

  const afterTurn = (res: Awaited<ReturnType<typeof adminApi.chatReply>>) => {
    setLastDecision(res.turn?.decision ?? null);
    if (res.ended) setEnded(true);
    qc.invalidateQueries({ queryKey: ['transcript', interviewId] });
    qc.invalidateQueries({ queryKey: ['application', appId] });
  };

  const start = useMutation({
    mutationFn: () => adminApi.chatStart(interviewId),
    onSuccess: afterTurn,
    onError: handleError,
  });

  const reply = useMutation({
    mutationFn: (text: string) => adminApi.chatReply(interviewId, text),
    onSuccess: afterTurn,
    onError: handleError,
  });

  const turns = transcript?.turns ?? [];
  const started = turns.length > 0;
  const busy = start.isPending || reply.isPending;

  const send = () => {
    const text = draft.trim();
    if (!text || busy || ended) return;
    setDraft('');
    reply.mutate(text);
  };

  if (llmMissing) {
    return (
      <EmptyState
        icon={<MessageSquare size={20} />}
        title="LLM provider not configured"
        description={llmMissing}
      />
    );
  }

  return (
    <Card padding="sm" className="flex flex-col" >
      <div className="flex-1 space-y-3 overflow-y-auto p-3" style={{ maxHeight: '55vh', minHeight: '200px' }}>
        {isLoading && <Skeleton className="h-24" />}
        {!isLoading && !started && (
          <EmptyState
            icon={<MessageSquare size={20} />}
            title="Text-mode interview"
            description="Run this interview as a text chat — Kandidly asks from the generated plan, decisions and transcript persist exactly like a voice session."
            action={
              <Button onClick={() => start.mutate()} disabled={busy}>
                {start.isPending ? 'Starting…' : 'Start interview'}
              </Button>
            }
          />
        )}
        {turns.map(turn => <TranscriptBubble key={turn.id} turn={turn} />)}
        {busy && (
          <div className="flex justify-start">
            <span className="text-xs px-4 py-2.5 rounded-xl animate-pulse"
              style={{ background: 'rgba(139,124,246,0.08)', color: 'var(--text-muted)' }}>
              Kandidly is thinking…
            </span>
          </div>
        )}
        {ended && (
          <div className="flex justify-center">
            <Badge color="emerald">Interview completed — scoring will run shortly</Badge>
          </div>
        )}
      </div>

      {started && !ended && (
        <div className="flex items-end gap-2 border-t p-3" style={{ borderColor: 'var(--border)' }}>
          <Textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            placeholder="Answer as the candidate… (Enter to send)"
            rows={2}
            className="flex-1"
          />
          <Button onClick={send} disabled={busy || !draft.trim()}>Send</Button>
        </div>
      )}
      {lastDecision && !ended && (
        <p className="px-3 pb-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          Last decision: <span className="uppercase tracking-wide">{lastDecision}</span>
        </p>
      )}
    </Card>
  );
}

// ─── Report tab ───────────────────────────────────────────────────────────────

function ScoreBar({ score, max = 5 }: { score: number; max?: number }) {
  const pct = (score / max) * 100;
  const color = score >= 4 ? '#34d399' : score >= 3 ? '#fbbf24' : '#f87171';
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ background: 'var(--surface-hover)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span
        className="text-xs font-semibold tabular w-8 text-right"
        style={{ color }}
      >
        {score.toFixed(1)}
      </span>
    </div>
  );
}

function ReportTab({
  interviewId,
  appId,
}: {
  interviewId: string;
  appId: string;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [reviewDecision, setReviewDecision] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');
  const [expandedEval, setExpandedEval] = useState<string | null>(null);

  const { data: report, isLoading, isError, error } = useQuery<ReportOut>({
    queryKey: ['report', interviewId],
    queryFn: () => adminApi.getReport(interviewId),
    retry: false,
  });

  const reviewMutation = useMutation({
    mutationFn: () => adminApi.reviewReport(interviewId, reviewDecision, reviewNotes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report', interviewId] });
      qc.invalidateQueries({ queryKey: ['application', appId] });
      toast('Review submitted', 'success');
    },
    onError: () => toast('Failed to submit review', 'error'),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  // 404 = not scored yet
  const isNotScored = isError && (error as { response?: { status?: number } })?.response?.status === 404;
  if (isNotScored) {
    return (
      <EmptyState
        icon={<BarChart2 size={20} />}
        title="Not scored yet"
        description="The report will appear here once AI scoring completes."
      />
    );
  }

  if (isError || !report) {
    return <ErrorState title="Couldn't load report" />;
  }

  const color = report.overall_score >= 4 ? '#34d399' : report.overall_score >= 3 ? '#fbbf24' : '#f87171';

  return (
    <div className="space-y-6">
      {/* Score header */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide mb-1" style={{ color: 'var(--text-muted)' }}>
              Overall score
            </p>
            <p className="text-5xl font-bold tabular" style={{ color }}>
              {report.overall_score.toFixed(1)}
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>out of 5.0</p>
          </div>
          <Badge color={
            report.status === 'final' ? 'emerald' :
            report.status === 'draft' ? 'amber' : 'zinc'
          }>
            {report.status}
          </Badge>
        </div>
        <p className="text-sm mt-4 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          {report.summary}
        </p>
      </Card>

      {/* Strengths & Concerns */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {report.strengths.length > 0 && (
          <Card>
            <p className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: 'var(--text-muted)' }}>
              Strengths
            </p>
            <ul className="space-y-2">
              {report.strengths.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <span className="text-emerald-400 mt-0.5">+</span>
                  {s}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {report.concerns.length > 0 && (
          <Card>
            <p className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: 'var(--text-muted)' }}>
              Concerns
            </p>
            <ul className="space-y-2">
              {report.concerns.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                  <span className="text-red-400 mt-0.5">−</span>
                  {c}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {/* Evaluations */}
      {report.evaluations.length > 0 && (
        <Card>
          <p className="text-xs font-medium uppercase tracking-wide mb-4" style={{ color: 'var(--text-muted)' }}>
            Criterion scores
          </p>
          <div className="space-y-4">
            {report.evaluations.map(ev => (
              <div key={ev.criterion_key}>
                <div className="flex items-center justify-between mb-1.5">
                  <button
                    className="text-sm font-medium text-left hover:underline"
                    style={{ color: 'var(--text-primary)' }}
                    onClick={() => setExpandedEval(prev => prev === ev.criterion_key ? null : ev.criterion_key)}
                  >
                    {ev.criterion_key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </button>
                </div>
                <ScoreBar score={ev.final_score} />
                {expandedEval === ev.criterion_key && (
                  <div className="mt-3 space-y-3 pl-3 border-l-2" style={{ borderColor: 'var(--accent)' }}>
                    <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{ev.rationale}</p>
                    {ev.evidence.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>Evidence</p>
                        {ev.evidence.map((e, i) => (
                          <p
                            key={i}
                            className="text-xs italic px-3 py-1.5 rounded"
                            style={{ background: 'var(--surface-hover)', color: 'var(--text-secondary)' }}
                          >
                            "{e}"
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Review form */}
      {report.status !== 'final' && (
        <Card>
          <p className="text-sm font-medium mb-4" style={{ color: 'var(--text-primary)' }}>
            Submit review decision
          </p>
          <div className="space-y-4">
            <Select
              label="Decision"
              placeholder="Select a decision…"
              value={reviewDecision}
              onChange={e => setReviewDecision(e.target.value)}
              options={[
                { value: 'advance',  label: 'Advance to next round' },
                { value: 'hold',     label: 'Hold / pending' },
                { value: 'reject',   label: 'Reject' },
              ]}
            />
            <Textarea
              label="Notes (optional)"
              placeholder="Additional context for the hiring team…"
              value={reviewNotes}
              onChange={e => setReviewNotes(e.target.value)}
              rows={3}
            />
            <div className="flex justify-end">
              <Button
                variant="primary"
                loading={reviewMutation.isPending}
                disabled={!reviewDecision}
                onClick={() => reviewMutation.mutate()}
              >
                Submit Review
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Already reviewed */}
      {report.status === 'final' && report.review_decision && (
        <Card>
          <p className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-muted)' }}>
            Review decision
          </p>
          <div className="flex items-center gap-2">
            <Badge color={
              report.review_decision === 'advance' ? 'emerald' :
              report.review_decision === 'reject'  ? 'red' : 'amber'
            }>
              {report.review_decision}
            </Badge>
          </div>
          {report.review_notes && (
            <p className="text-sm mt-3" style={{ color: 'var(--text-secondary)' }}>
              {report.review_notes}
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState('overview');

  const { data: app, isLoading, isError, refetch } = useQuery<AdminApplicationDetailOut>({
    queryKey: ['application', id],
    queryFn: () => adminApi.getApplication(id!),
    enabled: !!id,
  });

  const tabs = [
    { id: 'overview',   label: 'Overview' },
    { id: 'answers',    label: 'Form Answers' },
    { id: 'chat',       label: 'Interview (Text)' },
    { id: 'transcript', label: 'Transcript',  },
    { id: 'report',     label: 'Report' },
  ];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (isError || !app) {
    return <ErrorState title="Couldn't load application" onRetry={refetch} />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={app.candidate_name}
        description={app.candidate_email}
        back={
          <Link
            to={`/admin/requisitions/${app.requisition_id}`}
            className="inline-flex items-center gap-1.5 text-xs hover:underline"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft size={13} />
            Requisition
          </Link>
        }
        actions={<StateBadge state={app.state} />}
      />

      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'overview'   && <OverviewTab app={app} />}
      {activeTab === 'answers'    && <AnswersTab app={app} />}
      {activeTab === 'chat' && (
        app.interview_id
          ? <ChatTab interviewId={app.interview_id} appId={id!} />
          : <EmptyState
              icon={<MessageSquare size={20} />}
              title="No interview yet"
              description="A text interview becomes available once the candidate submits their form."
            />
      )}
      {activeTab === 'transcript' && (
        app.interview_id
          ? <TranscriptTab interviewId={app.interview_id} />
          : <EmptyState
              icon={<MessageSquare size={20} />}
              title="No interview yet"
              description="The candidate hasn't started their interview."
            />
      )}
      {activeTab === 'report' && (
        app.interview_id
          ? <ReportTab interviewId={app.interview_id} appId={id!} />
          : <EmptyState
              icon={<BarChart2 size={20} />}
              title="No interview yet"
              description="The candidate hasn't started their interview."
            />
      )}
    </div>
  );
}
