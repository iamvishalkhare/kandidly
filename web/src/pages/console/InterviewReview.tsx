/**
 * /console/interviews/:interviewId - review completed interview evidence.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Bot,
  Camera,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileText,
  Gauge,
  Pause,
  Play,
  ShieldCheck,
  UserCheck,
  XCircle,
} from 'lucide-react';
import { useWavesurfer } from '@wavesurfer/react';
import Hover from 'wavesurfer.js/plugins/hover';
import { cn } from '../../lib/utils';
import ConsoleLayout from './ConsoleLayout';
import { getInterviewReview } from './interviewData';
import type { InterviewReview as InterviewReviewData, TranscriptTurn } from './interviewData';

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

type ReviewDecision = 'Shortlist' | 'Reject' | 'Hold';

function formatTimeline(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function StatusPill({ status }: { status: string }) {
  const done = status === 'Done';

  return (
    <span
      className={cn(
        'inline-flex border px-2 py-1 label-mono',
        done
          ? 'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]'
          : 'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
      )}
    >
      {status}
    </span>
  );
}

function EvidenceMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface px-4 py-3">
      <p className="label-mono text-on-surface-variant">{label}</p>
      <p className="mt-1 text-on-surface font-medium">{value}</p>
    </div>
  );
}

function ScoreDistribution({ interview }: { interview: InterviewReviewData }) {
  const scores = [...interview.comparisonScores, interview.finalScore].sort((a, b) => a - b);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = Math.max(1, max - min);
  const candidateLeft = Math.min(96, Math.max(4, ((interview.finalScore - min) / range) * 100));

  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge size={16} className="text-primary-fixed-dim" />
          <h2 className="label-mono text-on-surface">Candidate Standing</h2>
        </div>
        <span className="label-mono text-primary-fixed-dim">{interview.percentile}th percentile</span>
      </div>
      <div className="p-4 space-y-4">
        <div className="relative h-28 border border-outline-variant bg-surface-container-lowest">
          <div className="absolute inset-x-4 bottom-8 flex items-end gap-1">
            {scores.map((score, i) => (
              <div
                key={`${score}-${i}`}
                className={cn(
                  'flex-1 bg-surface-container-highest',
                  score === interview.finalScore && 'bg-primary-container',
                )}
                style={{ height: `${30 + ((score - min) / range) * 46}px` }}
              />
            ))}
          </div>
          <div
            className="absolute top-3 bottom-3 w-px bg-primary-fixed-dim"
            style={{ left: `${candidateLeft}%` }}
          />
          <div
            className="absolute top-3 -translate-x-1/2 border border-primary-container bg-surface px-2 py-1 label-mono text-primary-fixed-dim"
            style={{ left: `${candidateLeft}%` }}
          >
            {interview.finalScore}
          </div>
          <div className="absolute left-4 right-4 bottom-3 flex justify-between label-mono text-on-surface-variant">
            <span>{min}</span>
            <span>{max}</span>
          </div>
        </div>
        <p className="text-sm text-on-surface-variant">
          Compared with candidates who completed {interview.requisitionId} / {interview.requisitionTitle}.
        </p>
      </div>
    </section>
  );
}

function WaveformRecording({
  interview,
  currentSeconds,
  onSeek,
}: {
  interview: InterviewReviewData;
  currentSeconds: number;
  onSeek: (seconds: number) => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const waveformRef = useRef<HTMLDivElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const durationSeconds = Math.max(1, interview.transcript.at(-1)?.seconds ?? 1);

  // Placeholder amplitude data until real recordings are wired up — swap for exportPeaks() from the actual audio.
  const peaks = useMemo(
    () => [Array.from({ length: 200 }, (_, i) => (24 + ((i * 17 + i * i * 3) % 58)) / 100)],
    [],
  );
  const plugins = useMemo(
    () => [
      Hover.create({
        lineColor: '#b8c3ff',
        lineWidth: 1,
        labelBackground: '#0c0e17',
        labelColor: '#c4c5d9',
        labelSize: 11,
      }),
    ],
    [],
  );

  const { wavesurfer } = useWavesurfer({
    container: waveformRef,
    height: 'auto',
    barWidth: 3,
    barGap: 2,
    cursorWidth: 1,
    waveColor: '#33343e',
    progressColor: '#2e5bff',
    cursorColor: '#b8c3ff',
    normalize: true,
    peaks,
    duration: durationSeconds,
    plugins,
  });

  // The waveform is driven by peaks/duration only (no real media), so it stays a controlled
  // component: external seeks move the cursor, and user drags/clicks report back via onSeek.
  useEffect(() => {
    wavesurfer?.setTime(currentSeconds);
  }, [wavesurfer, currentSeconds]);

  useEffect(() => {
    return wavesurfer?.on('interaction', newTime => onSeek(newTime));
  }, [wavesurfer, onSeek]);

  const seekAudio = (seconds: number) => {
    if (audioRef.current && Number.isFinite(audioRef.current.duration) && audioRef.current.duration > seconds) {
      audioRef.current.currentTime = seconds;
    }
  };

  const togglePlayback = async () => {
    if (!audioRef.current) return;

    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
      return;
    }

    seekAudio(currentSeconds);
    await audioRef.current.play().catch(() => undefined);
    setPlaying(!audioRef.current.paused);
  };

  return (
    <div className="mt-5 border-t border-outline-variant pt-4 text-left">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="label-mono text-on-surface-variant">Recording Timeline</p>
          <p className="label-mono text-primary-fixed-dim mt-1">
            {formatTimeline(currentSeconds)} / {formatTimeline(durationSeconds)}
          </p>
        </div>
        <button
          type="button"
          onClick={togglePlayback}
          className="size-9 shrink-0 border border-outline-variant text-on-surface-variant hover:border-primary-container hover:text-primary-fixed-dim transition-colors duration-150 flex items-center justify-center"
          aria-label={playing ? 'Pause recording' : 'Play recording'}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>

      <div
        ref={waveformRef}
        role="slider"
        aria-label="Seek interview recording"
        aria-valuemin={0}
        aria-valuemax={durationSeconds}
        aria-valuenow={currentSeconds}
        className="mt-3 h-24 w-full border border-outline-variant bg-surface px-2 overflow-hidden"
      />

      <div className="mt-2 flex justify-between label-mono text-on-surface-variant">
        <span>0:00</span>
        <span>{formatTimeline(durationSeconds)}</span>
      </div>
      <audio
        ref={audioRef}
        src={interview.audioSrc}
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
        className="hidden"
      />
    </div>
  );
}

function AudioTranscript({
  interview,
  activeTranscriptId,
  onJump,
  transcriptRefs,
}: {
  interview: InterviewReviewData;
  activeTranscriptId: string;
  onJump: (turn: TranscriptTurn) => void;
  transcriptRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
}) {
  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center gap-2">
        <FileText size={16} className="text-primary-fixed-dim" />
        <h2 className="label-mono text-on-surface">Transcript</h2>
      </div>
      <div className="max-h-[560px] overflow-y-auto divide-y divide-outline-variant">
        {interview.transcript.map(turn => (
          <div
            key={turn.id}
            ref={node => {
              transcriptRefs.current[turn.id] = node;
            }}
            className={cn(
              'grid grid-cols-1 md:grid-cols-[96px_120px_1fr] gap-3 px-4 py-4 transition-colors duration-150',
              activeTranscriptId === turn.id ? 'bg-primary-container/10' : 'bg-surface',
            )}
          >
            <button
              type="button"
              onClick={() => onJump(turn)}
              className="label-mono text-primary-fixed-dim text-left hover:text-on-surface"
            >
              {turn.at}
            </button>
            <div className="flex items-center gap-2 label-mono text-on-surface-variant">
              {turn.speaker === 'AI' ? <Bot size={14} /> : <UserCheck size={14} />}
              {turn.speaker}
            </div>
            <p className="text-on-surface">{turn.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProctorRoll({ interview }: { interview: InterviewReviewData }) {
  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Camera size={16} className="text-primary-fixed-dim" />
          <h2 className="label-mono text-on-surface">Proctored Images</h2>
        </div>
        <span className="label-mono text-on-surface-variant">10 second interval</span>
      </div>
      {interview.proctorFrames.length > 0 ? (
        <div className="flex gap-3 overflow-x-auto p-4">
          {interview.proctorFrames.map((frame, i) => (
            <div key={frame.id} className="w-40 shrink-0 border border-outline-variant bg-surface-container-lowest">
              <div
                className="h-28 border-b border-outline-variant relative overflow-hidden"
                role="img"
                aria-label={`Proctor frame at ${frame.at}`}
                style={{
                  background:
                    `linear-gradient(135deg, rgba(46,91,255,${0.10 + (i % 4) * 0.04}), transparent 48%), ` +
                    `linear-gradient(180deg, #282933, #11131c)`,
                }}
              >
                <div className="absolute left-1/2 top-6 size-8 -translate-x-1/2 border border-outline-variant bg-surface-container-highest" />
                <div className="absolute left-8 right-8 bottom-4 h-10 border border-outline-variant bg-surface-container-high" />
                <div className="absolute inset-x-0 bottom-0 h-px bg-primary-container/50" />
              </div>
              <div className="p-2">
                <p className="label-mono text-on-surface">{frame.at}</p>
                <p
                  className={cn(
                    'mt-1 label-mono',
                    frame.signal === 'Clear' ? 'text-[var(--emerald-chip-text)]' : 'text-[var(--amber-chip-text)]',
                  )}
                >
                  {frame.signal}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-8 text-center label-mono text-on-surface-variant">
          No proctor frames available for this interview.
        </div>
      )}
    </section>
  );
}

function RubricAssessment({ interview }: { interview: InterviewReviewData }) {
  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center gap-2">
        <ShieldCheck size={16} className="text-primary-fixed-dim" />
        <h2 className="label-mono text-on-surface">AI Assessment Against Rubric</h2>
      </div>
      <div className="divide-y divide-outline-variant">
        {interview.rubric.map(item => (
          <details key={item.id} className="group bg-surface">
            <summary className="cursor-pointer list-none grid grid-cols-1 md:grid-cols-[1fr_120px_120px_24px] gap-3 px-4 py-4 items-center hover:bg-surface-container transition-colors duration-150">
              <div>
                <p className="font-medium text-on-surface">{item.label}</p>
                <p className="text-sm text-on-surface-variant mt-1">{item.summary}</p>
              </div>
              <p className="label-mono text-on-surface-variant">Weight {item.weight}%</p>
              <p className="label-mono text-primary-fixed-dim">{item.score} / 100</p>
              <ChevronDown size={16} className="text-on-surface-variant transition-transform duration-150 group-open:rotate-180" />
            </summary>
            <div className="px-4 pb-4 md:pl-8">
              <div className="border-l border-primary-container pl-4 text-on-surface-variant">
                {item.reasoning}
              </div>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

export default function InterviewReview() {
  const { interviewId } = useParams<{ interviewId: string }>();
  const interview = getInterviewReview(interviewId);
  const transcriptRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [activeTranscriptId, setActiveTranscriptId] = useState(interview?.transcript[0]?.id ?? '');
  const [currentSeconds, setCurrentSeconds] = useState(interview?.transcript[0]?.seconds ?? 0);
  const [decision, setDecision] = useState<ReviewDecision | null>(null);

  const recommendedDecision = useMemo<ReviewDecision | null>(() => {
    if (!interview) return null;
    return interview.recommendation;
  }, [interview]);

  if (!interview) {
    return (
      <ConsoleLayout>
        <div className="p-8 max-w-3xl">
          <Link to="/console/interviews" className="inline-flex items-center gap-2 label-mono text-on-surface-variant hover:text-primary-fixed-dim">
            <ArrowLeft size={16} />
            Back to interviews
          </Link>
          <div className="mt-8 border border-outline-variant bg-surface p-8">
            <p className="label-mono text-error">Interview not found</p>
            <p className="mt-2 text-on-surface-variant">The requested interview review does not exist in the current dataset.</p>
          </div>
        </div>
      </ConsoleLayout>
    );
  }

  const jumpToTranscript = (turn: TranscriptTurn) => {
    setCurrentSeconds(turn.seconds);
    setActiveTranscriptId(turn.id);
    transcriptRefs.current[turn.id]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const jumpToTimeline = (seconds: number) => {
    const turn = interview.transcript.reduce((best, candidate) => {
      const bestDistance = Math.abs(best.seconds - seconds);
      const candidateDistance = Math.abs(candidate.seconds - seconds);
      return candidateDistance < bestDistance ? candidate : best;
    }, interview.transcript[0]);

    setCurrentSeconds(seconds);
    setActiveTranscriptId(turn.id);
  };

  return (
    <ConsoleLayout>
      <header className="border-b border-outline-variant bg-surface px-4 py-4 sticky top-0 z-30">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <Link to="/console/interviews" className="inline-flex items-center gap-2 label-mono text-on-surface-variant hover:text-primary-fixed-dim">
              <ArrowLeft size={16} />
              Interviews
            </Link>
            <h1 className="font-display text-headline-lg text-on-surface tracking-tight mt-2">{interview.candidateName}</h1>
            <p className="label-mono text-on-surface-variant mt-1">
              {interview.id.toUpperCase()} / {interview.requisitionId} / {interview.requisitionTitle}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(['Shortlist', 'Hold', 'Reject'] as const).map(action => (
              <button
                key={action}
                type="button"
                onClick={() => setDecision(action)}
                className={cn(
                  'h-10 px-4 border label-mono transition-colors duration-150 flex items-center gap-2',
                  decision === action
                    ? 'border-primary-container bg-primary-container text-on-primary-container'
                    : 'border-outline-variant text-on-surface-variant hover:border-primary-container hover:text-primary-fixed-dim',
                )}
              >
                {action === 'Reject' ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
                {action}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="p-4 flex-1 space-y-4">
        <section className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-px bg-outline-variant border border-outline-variant">
          <div className="bg-surface p-5">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill status={interview.scoringStatus} />
                  <span className="inline-flex border border-primary-container px-2 py-1 label-mono text-primary-fixed-dim">
                    AI recommends {recommendedDecision}
                  </span>
                  {decision && (
                    <span className="inline-flex border border-outline-variant px-2 py-1 label-mono text-on-surface-variant">
                      Review marked {decision}
                    </span>
                  )}
                </div>
                <p className="mt-4 text-body-md text-on-surface max-w-3xl">{interview.assessmentSummary}</p>
              </div>
              <div className="shrink-0 w-full md:w-[420px] border border-outline-variant bg-surface-container-lowest px-5 py-4 text-center">
                <p className="label-mono text-on-surface-variant">Final Score</p>
                <p className="font-display text-[56px] leading-none font-bold text-primary-fixed-dim tabular mt-2">{interview.finalScore}</p>
                <p className="label-mono text-on-surface-variant mt-1">out of 100</p>
              </div>
            </div>
            <WaveformRecording
              interview={interview}
              currentSeconds={currentSeconds}
              onSeek={jumpToTimeline}
            />
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-1 gap-px bg-outline-variant">
            <EvidenceMetric label="Candidate" value={interview.candidateName} />
            <EvidenceMetric label="Domain" value={interview.domain} />
            <EvidenceMetric label="Scoring" value={interview.scoringStatus} />
            <EvidenceMetric label="Taken On" value={dateTimeFormatter.format(new Date(interview.concludedAt))} />
            <EvidenceMetric label="Duration" value={interview.duration} />
            <EvidenceMetric label="Requisition ID" value={interview.requisitionId} />
          </div>
        </section>

        <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_420px] gap-4">
          <div className="space-y-4">
            <AudioTranscript
              interview={interview}
              activeTranscriptId={activeTranscriptId}
              onJump={jumpToTranscript}
              transcriptRefs={transcriptRefs}
            />
            <RubricAssessment interview={interview} />
          </div>
          <div className="space-y-4 2xl:sticky 2xl:top-24 self-start">
            <ScoreDistribution interview={interview} />
            <ProctorRoll interview={interview} />
            <section className="border border-outline-variant bg-surface">
              <div className="border-b border-outline-variant px-4 py-3 flex items-center gap-2">
                <Clock3 size={16} className="text-primary-fixed-dim" />
                <h2 className="label-mono text-on-surface">Review Trail</h2>
              </div>
              <div className="p-4 space-y-3 text-sm text-on-surface-variant">
                <p>Assessment generated after transcript scoring completed.</p>
                <p>Decision state is local until the review API is connected.</p>
              </div>
            </section>
          </div>
        </div>
      </div>
    </ConsoleLayout>
  );
}
