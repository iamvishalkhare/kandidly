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
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Gauge,
  Eye,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  ShieldCheck,
  UserCheck,
  XCircle,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useWavesurfer } from '@wavesurfer/react';
import Hover from 'wavesurfer.js/plugins/hover';
import { cn } from '../../lib/utils';
import { Modal, useToast } from '../../components/ui';
import ConsoleLayout from './ConsoleLayout';
import type {
  IntegrityBand,
  IntegritySummary,
  IntegrityVerdict,
  ProctorFrame,
  ScreeningAnswer,
  TranscriptTurn,
} from './interviewData';
import {
  useConsoleReview,
  useProctorFrames,
  useReviewDecision,
  type ReviewData,
} from '../../lib/consoleApi';

type InterviewReviewData = ReviewData;

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

type ReviewDecision = 'Shortlist' | 'Reject' | 'Hold';

// Decision buttons stay in their semantic color; the chosen one is filled.
const DECISION_BUTTON_CLASS: Record<ReviewDecision, { idle: string; active: string }> = {
  Shortlist: {
    idle: 'border-outline-variant text-[var(--emerald-chip-text)] hover:border-[var(--emerald-chip-text)] hover:bg-[var(--emerald-chip-bg)]',
    active:
      'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]',
  },
  Hold: {
    idle: 'border-outline-variant text-[var(--amber-chip-text)] hover:border-[var(--amber-chip-text)] hover:bg-[var(--amber-chip-bg)]',
    active:
      'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
  },
  Reject: {
    idle: 'border-outline-variant text-[var(--red-chip-text)] hover:border-[var(--red-chip-text)] hover:bg-[var(--red-chip-bg)]',
    active: 'border-[var(--red-chip-text)] bg-[var(--red-chip-bg)] text-[var(--red-chip-text)]',
  },
};

function formatTimeline(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function formatTranscriptSpeaker(turn: TranscriptTurn, candidateName: string) {
  return turn.speaker === 'AI' ? 'Kandidly AI' : candidateName;
}

function safeFilenamePart(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function buildTranscriptText(interview: InterviewReviewData) {
  const takenOn = interview.concludedAt
    ? dateTimeFormatter.format(new Date(interview.concludedAt))
    : 'Unavailable';
  const lines = [
    'Transcript',
    `Candidate: ${interview.candidateName}`,
    `Email: ${interview.candidateEmail ?? 'Unavailable'}`,
    `Requisition: ${interview.requisitionId} - ${interview.requisitionTitle}`,
    `Taken On: ${takenOn}`,
    '',
    ...interview.transcript.map(
      turn => `[${turn.at}] ${formatTranscriptSpeaker(turn, interview.candidateName)}: ${turn.text}`,
    ),
  ];

  return `${lines.join('\n')}\n`;
}

function transcriptFilename(interview: InterviewReviewData) {
  const candidate = safeFilenamePart(interview.candidateName) || 'candidate';
  const code = safeFilenamePart(interview.code ?? interview.id) || 'interview';
  return `${candidate}-${code}-transcript.txt`;
}

function StatusPill({ status }: { status: string }) {
  const done = status === 'Done';

  return (
    <span
      className={cn(
        'inline-flex border px-2 py-1 label-mono',
        done
          ? 'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]'
          : 'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)] animate-pulse',
      )}
    >
      {status}
    </span>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard unavailable (insecure context) — nothing to copy to */
        }
      }}
      aria-label={label}
      title={label}
      className="shrink-0 text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-150"
    >
      {copied ? <Check size={14} className="text-[var(--emerald-chip-text)]" /> : <Copy size={14} />}
    </button>
  );
}

/** Labeled copy button for larger text blocks (e.g. the assessment summary). */
function CopyTextButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard unavailable (insecure context) — nothing to copy to */
        }
      }}
      className="inline-flex items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-on-surface-variant hover:text-primary-fixed-dim hover:border-primary-container transition-colors duration-150"
    >
      {copied ? (
        <Check size={14} className="text-[var(--emerald-chip-text)]" />
      ) : (
        <Copy size={14} />
      )}
      {copied ? 'Copied' : label}
    </button>
  );
}

/** Lobby verification selfie. The presigned URL rotates on every review
 * refetch, so pin the first one — otherwise the 4–10s evaluation polls would
 * re-fetch the image over and over. onError adopts the newest signature
 * (fresh presign after the 10-min expiry). */
function CandidatePhoto({ url, alt }: { url?: string | null; alt: string }) {
  const pinnedRef = useRef<string | null>(null);
  const [, bump] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  if (!pinnedRef.current && url) pinnedRef.current = url;
  if (!pinnedRef.current) return null;
  const onError = () => {
    if (url && url !== pinnedRef.current) {
      pinnedRef.current = url;
      bump(n => n + 1);
    }
  };
  return (
    <>
      <button
        type="button"
        onClick={() => setZoomed(true)}
        aria-label={`Enlarge ${alt}`}
        className="size-24 shrink-0 cursor-zoom-in border border-outline-variant bg-surface-container-lowest"
      >
        <img
          src={pinnedRef.current}
          alt={alt}
          onError={onError}
          className="size-full object-cover"
        />
      </button>
      <Modal open={zoomed} onClose={() => setZoomed(false)} title={alt} size="lg">
        <img
          src={pinnedRef.current}
          alt={alt}
          onError={onError}
          className="w-full max-h-[70vh] object-contain border border-outline-variant bg-surface-container-lowest"
        />
      </Modal>
    </>
  );
}

function EvidenceMetric({
  label,
  value,
  sub,
  copyableSub = false,
}: {
  label: string;
  value: string;
  sub?: string | null;
  copyableSub?: boolean;
}) {
  return (
    <div className="bg-surface px-4 py-3">
      <p className="label-mono text-on-surface-variant">{label}</p>
      <p className="mt-1 text-on-surface font-medium">{value}</p>
      {sub && (
        <div className="mt-0.5 flex items-center gap-2">
          <p className="text-sm text-on-surface-variant break-all">{sub}</p>
          {copyableSub && <CopyButton text={sub} label={`Copy ${sub}`} />}
        </div>
      )}
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

const PLAYBACK_RATES = [1, 1.25, 1.5, 2];

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
  const [rate, setRate] = useState(1);
  const queryClient = useQueryClient();
  const audioErrorsRef = useRef(0);
  // audioSrc is re-presigned on every review refetch (fresh signature each
  // time), and the evaluation/integrity polls refetch every 4–10s. Binding it
  // straight to <audio src> resets the element on each poll, so playback
  // could never survive more than a few seconds. Pin the first URL for this
  // mount; onError drops the pin so the next refetched URL (fresh signature
  // after the 10-min presign expiry) takes over.
  const pinnedAudioSrcRef = useRef<string | null>(null);
  if (interview.audioSrc && !pinnedAudioSrcRef.current) {
    pinnedAudioSrcRef.current = interview.audioSrc;
  }
  const audioSrc = pinnedAudioSrcRef.current;
  const durationSeconds = Math.max(
    1,
    interview.audioDurationSeconds ?? interview.transcript.at(-1)?.seconds ?? 1,
  );

  // Real recording peaks when available (0–100 ints from the backend);
  // deterministic placeholder bars otherwise so the timeline stays usable.
  const peaks = useMemo(() => {
    if (interview.waveformPeaks?.length) {
      return [interview.waveformPeaks.map(v => Math.max(0.02, v / 100))];
    }
    return [Array.from({ length: 200 }, (_, i) => (24 + ((i * 17 + i * i * 3) % 58)) / 100)];
  }, [interview.waveformPeaks]);
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

  // The waveform stays a controlled visualization (peaks/duration only, no
  // media bound): external seeks move the cursor AND the hidden audio element
  // (drift-corrected so transcript/waveform clicks work mid-playback), while
  // the audio's own progress drives currentSeconds via onTimeUpdate.
  useEffect(() => {
    wavesurfer?.setTime(currentSeconds);
    const audio = audioRef.current;
    if (
      audio &&
      Number.isFinite(audio.duration) &&
      Math.abs(audio.currentTime - currentSeconds) > 1.5
    ) {
      audio.currentTime = Math.min(Math.max(0, currentSeconds), Math.max(0, audio.duration - 0.05));
    }
  }, [wavesurfer, currentSeconds]);

  useEffect(() => {
    return wavesurfer?.on('interaction', newTime => onSeek(newTime));
  }, [wavesurfer, onSeek]);

  const togglePlayback = async () => {
    if (!audioRef.current) return;

    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
      return;
    }

    audioRef.current.playbackRate = rate;
    if (
      Number.isFinite(audioRef.current.duration) &&
      Math.abs(audioRef.current.currentTime - currentSeconds) > 1.5
    ) {
      audioRef.current.currentTime = Math.min(currentSeconds, audioRef.current.duration - 0.05);
    }
    await audioRef.current.play().catch(() => undefined);
    setPlaying(!audioRef.current.paused);
  };

  const skip = (delta: number) => {
    onSeek(Math.min(durationSeconds, Math.max(0, currentSeconds + delta)));
  };

  const cycleRate = () => {
    const next = PLAYBACK_RATES[(PLAYBACK_RATES.indexOf(rate) + 1) % PLAYBACK_RATES.length];
    setRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  };

  // Keyboard transport: Space play/pause, ←/→ ±10s, Shift+←/→ ±30s. The
  // handler lives in a ref so the window listener is attached exactly once.
  const keyHandlerRef = useRef<(e: KeyboardEvent) => void>(() => {});
  keyHandlerRef.current = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable)
    ) {
      return;
    }
    if (e.code === 'Space') {
      e.preventDefault();
      void togglePlayback();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      skip(e.shiftKey ? -30 : -10);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      skip(e.shiftKey ? 30 : 10);
    }
  };
  useEffect(() => {
    const listener = (e: KeyboardEvent) => keyHandlerRef.current(e);
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);

  const transportButton =
    'size-9 shrink-0 border border-outline-variant text-on-surface-variant hover:border-primary-container hover:text-primary-fixed-dim transition-colors duration-150 flex items-center justify-center';

  return (
    <div className="mt-5 border-t border-outline-variant pt-4 text-left">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="label-mono text-on-surface-variant">Recording Timeline</p>
          <p className="label-mono text-primary-fixed-dim mt-1">
            {formatTimeline(currentSeconds)} / {formatTimeline(durationSeconds)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => skip(-10)}
            className={transportButton}
            aria-label="Back 10 seconds"
            title="Back 10s (←)"
          >
            <RotateCcw size={15} />
          </button>
          <button
            type="button"
            onClick={togglePlayback}
            className={transportButton}
            aria-label={playing ? 'Pause recording' : 'Play recording'}
            title="Play/Pause (Space)"
          >
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button
            type="button"
            onClick={() => skip(10)}
            className={transportButton}
            aria-label="Forward 10 seconds"
            title="Forward 10s (→)"
          >
            <RotateCw size={15} />
          </button>
          <button
            type="button"
            onClick={cycleRate}
            className={cn(transportButton, 'w-12 label-mono tabular')}
            aria-label={`Playback speed ${rate}x`}
            title="Cycle playback speed"
          >
            {rate}×
          </button>
        </div>
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
      {audioSrc && (
        <audio
          ref={audioRef}
          src={audioSrc}
          preload="auto"
          onTimeUpdate={e => {
            if (!e.currentTarget.paused) onSeek(e.currentTarget.currentTime);
          }}
          onPlay={e => {
            e.currentTarget.playbackRate = rate;
            setPlaying(true);
          }}
          onEnded={() => setPlaying(false)}
          onPause={() => setPlaying(false)}
          onError={() => {
            // The presigned URL expires after 10 minutes; refetching the
            // review mints a fresh one, and dropping the pin lets it replace
            // the dead src. Cap invalidations so a genuinely missing file
            // doesn't refetch-loop.
            if (audioErrorsRef.current < 2) {
              audioErrorsRef.current += 1;
              pinnedAudioSrcRef.current = null;
              void queryClient.invalidateQueries({
                queryKey: ['console', 'interviews', interview.id],
              });
            }
          }}
          className="hidden"
        />
      )}
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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const userScrollingRef = useRef(false);
  const programmaticRef = useRef(false);
  const scrollIdleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleDownloadTranscript = () => {
    const blob = new Blob([buildTranscriptText(interview)], { type: 'text/plain;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = transcriptFilename(interview);
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
  };

  // Manual scrolling suppresses auto-follow for a few seconds so the reader
  // isn't yanked back to the playhead mid-read.
  const handleScroll = () => {
    if (programmaticRef.current) return;
    userScrollingRef.current = true;
    if (scrollIdleTimer.current) clearTimeout(scrollIdleTimer.current);
    scrollIdleTimer.current = setTimeout(() => {
      userScrollingRef.current = false;
    }, 3000);
  };

  // Keep the active row centered — scrolling only this container (never
  // scrollIntoView, which would drag the page under the sticky header).
  useEffect(() => {
    if (!activeTranscriptId || userScrollingRef.current) return;
    const container = containerRef.current;
    const row = transcriptRefs.current[activeTranscriptId];
    if (!container || !row) return;
    const rowTop =
      row.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop;
    programmaticRef.current = true;
    container.scrollTo({
      top: rowTop - container.clientHeight / 2 + row.clientHeight / 2,
      behavior: 'smooth',
    });
    // Smooth scroll emits many scroll events; release the flag once settled.
    const settle = setTimeout(() => {
      programmaticRef.current = false;
    }, 600);
    return () => clearTimeout(settle);
  }, [activeTranscriptId, transcriptRefs]);

  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={16} className="shrink-0 text-primary-fixed-dim" />
          <h2 className="label-mono text-on-surface">Transcript</h2>
        </div>
        <button
          type="button"
          onClick={handleDownloadTranscript}
          className="inline-flex shrink-0 items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-on-surface-variant hover:text-primary-fixed-dim hover:border-primary-container transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={interview.transcript.length === 0}
        >
          <Download size={14} />
          Download .txt
        </button>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="max-h-[560px] overflow-y-auto divide-y divide-outline-variant"
      >
        {interview.transcript.map(turn => (
          <div
            key={turn.id}
            ref={node => {
              transcriptRefs.current[turn.id] = node;
            }}
            className={cn(
              'grid grid-cols-1 md:grid-cols-[96px_160px_1fr] gap-3 px-4 py-4 transition-colors duration-150',
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
            <div className="flex items-center gap-2 label-mono text-on-surface-variant min-w-0">
              {turn.speaker === 'AI' ? (
                <Bot size={14} className="shrink-0" />
              ) : (
                <UserCheck size={14} className="shrink-0" />
              )}
              <span
                className="truncate"
                title={formatTranscriptSpeaker(turn, interview.candidateName)}
              >
                {formatTranscriptSpeaker(turn, interview.candidateName)}
              </span>
            </div>
            <p className="text-on-surface">{turn.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

const INTEGRITY_CHIP: Record<IntegrityVerdict, { label: string; className: string }> = {
  clear: {
    label: 'Integrity: Clear',
    className:
      'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]',
  },
  warn: {
    label: 'Integrity: Review',
    className:
      'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
  },
  flagged: {
    label: 'Integrity: Flagged',
    className: 'border-[var(--red-chip-text)] bg-[var(--red-chip-bg)] text-[var(--red-chip-text)]',
  },
  pending: {
    label: 'Integrity: Pending',
    className: 'border-outline-variant text-on-surface-variant animate-pulse',
  },
};

function signalClass(signal: ProctorFrame['signal']): string {
  if (signal === 'Pending') return 'text-on-surface-variant';
  if (signal === 'Clear') return 'text-[var(--emerald-chip-text)]';
  if (signal === 'No face' || signal === 'Multiple faces') return 'text-[var(--red-chip-text)]';
  return 'text-[var(--amber-chip-text)]';
}

// Band drives the chip color only; the label shows just the score.
const INTEGRITY_BAND_CLASS: Record<IntegrityBand, string> = {
  '90-100':
    'border-[var(--emerald-chip-text)] bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)]',
  '60-89':
    'border-[var(--amber-chip-text)] bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)]',
  '40-59': 'border-[var(--red-chip-text)] bg-[var(--red-chip-bg)] text-[var(--red-chip-text)]',
  'under-40': 'border-[var(--red-chip-text)] bg-[var(--red-chip-bg)] text-[var(--red-chip-text)]',
};

function integrityChip(
  integrity: IntegritySummary | null,
  analyzing: boolean,
): { label: string; className: string } | null {
  if (!integrity) return null;
  // Proctoring was off for this requisition: no camera data was ever expected,
  // so a clear/flagged verdict would be misleading either way.
  if (integrity.proctoringEnabled === false) {
    return {
      label: 'Proctoring off',
      className: 'border-outline-variant text-on-surface-variant',
    };
  }
  if (integrity.score != null && integrity.band) {
    return {
      label: `Integrity ${integrity.score}/100`,
      className: INTEGRITY_BAND_CLASS[integrity.band],
    };
  }
  if (analyzing) {
    return {
      label: 'Integrity: Analyzing…',
      className: 'border-outline-variant text-on-surface-variant animate-pulse',
    };
  }
  return INTEGRITY_CHIP[integrity.verdict];
}

function ProctorRoll({ interview }: { interview: InterviewReviewData }) {
  const [zoomFrame, setZoomFrame] = useState<ProctorFrame | null>(null);
  const integrity = interview.integrity;
  // Frame analysis has started but the final LLM verdict hasn't landed yet.
  const analyzing =
    !!integrity &&
    integrity.frameCount > 0 &&
    integrity.analyzedCount > 0 &&
    integrity.score == null;
  const chip = integrityChip(integrity, analyzing);

  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useProctorFrames(
    interview.id,
    analyzing,
  );
  const frames = data?.frames ?? [];
  const frameCount = integrity?.frameCount ?? data?.total ?? 0;

  // Infinite scroll: fetch the next page when the sentinel at the right end
  // of the strip comes within one viewport of view.
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const root = scrollerRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel) return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(entry => entry.isIntersecting) && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { root, rootMargin: '0px 480px 0px 0px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, frames.length]);

  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Camera size={16} className="text-primary-fixed-dim" />
          <h2 className="label-mono text-on-surface">Proctored Images</h2>
        </div>
        <div className="flex items-center gap-2">
          {chip && (
            <span className={cn('inline-flex border px-2 py-1 label-mono', chip.className)}>
              {chip.label}
            </span>
          )}
          {integrity?.proctoringEnabled !== false && (
            <span className="label-mono text-on-surface-variant">
              {integrity && integrity.frameCount > 0
                ? `${integrity.analyzedCount}/${integrity.frameCount} analyzed`
                : `${frameCount} frames`}
            </span>
          )}
        </div>
      </div>
      {integrity?.summary && (
        <p className="border-b border-outline-variant px-4 py-3 text-sm text-on-surface-variant">
          {integrity.summary}
        </p>
      )}
      {frames.length > 0 ? (
        <div ref={scrollerRef} className="flex gap-3 overflow-x-auto p-4">
          {frames.map((frame, i) => (
            <div key={frame.id} className="w-40 shrink-0 border border-outline-variant bg-surface-container-lowest">
              <button
                type="button"
                onClick={() => setZoomFrame(frame)}
                className="block h-28 w-full border-b border-outline-variant relative overflow-hidden cursor-zoom-in"
                aria-label={`Enlarge proctor frame at ${frame.at}`}
                style={{
                  background:
                    `linear-gradient(135deg, rgba(46,91,255,${0.10 + (i % 4) * 0.04}), transparent 48%), ` +
                    `linear-gradient(180deg, #282933, #11131c)`,
                }}
              >
                {frame.imageUrl ? (
                  <img
                    src={frame.imageUrl}
                    alt={`Proctor frame at ${frame.at}`}
                    className="absolute inset-0 h-full w-full object-cover"
                  />
                ) : (
                  <>
                    <div className="absolute left-1/2 top-6 size-8 -translate-x-1/2 border border-outline-variant bg-surface-container-highest" />
                    <div className="absolute left-8 right-8 bottom-4 h-10 border border-outline-variant bg-surface-container-high" />
                  </>
                )}
                <div className="absolute inset-x-0 bottom-0 h-px bg-primary-container/50" />
              </button>
              <div className="p-2">
                <p className="label-mono text-on-surface">{frame.at}</p>
                <p className={cn('mt-1 label-mono', signalClass(frame.signal))}>{frame.signal}</p>
                {frame.note && (
                  <p className="mt-1 text-xs text-on-surface-variant truncate" title={frame.note}>
                    {frame.note}
                  </p>
                )}
              </div>
            </div>
          ))}
          {(hasNextPage || isFetchingNextPage) && (
            <div className="w-40 h-28 shrink-0 self-start border border-outline-variant bg-surface-container-lowest flex items-center justify-center">
              <span className="label-mono text-on-surface-variant animate-pulse">Loading…</span>
            </div>
          )}
          <div ref={sentinelRef} className="w-px shrink-0 self-stretch" aria-hidden />
        </div>
      ) : (
        <div className="p-8 text-center label-mono text-on-surface-variant">
          {integrity?.proctoringEnabled === false
            ? 'Proctoring was disabled for this requisition — no camera data was collected.'
            : isLoading
              ? 'Loading proctor frames…'
              : 'No proctor frames available for this interview.'}
        </div>
      )}

      <Modal
        open={zoomFrame !== null}
        onClose={() => setZoomFrame(null)}
        title={zoomFrame ? `Proctor frame — ${zoomFrame.at}` : undefined}
        size="lg"
      >
        {zoomFrame && (
          <div className="space-y-3">
            {zoomFrame.imageUrl ? (
              <img
                src={zoomFrame.imageUrl}
                alt={`Proctor frame at ${zoomFrame.at}`}
                className="w-full max-h-[60vh] object-contain border border-outline-variant bg-surface-container-lowest"
              />
            ) : (
              <div className="p-8 text-center label-mono text-on-surface-variant border border-outline-variant">
                Image unavailable
              </div>
            )}
            <div className="flex items-center justify-between gap-3">
              <p className={cn('label-mono', signalClass(zoomFrame.signal))}>{zoomFrame.signal}</p>
              <p className="label-mono text-on-surface-variant">{zoomFrame.at}</p>
            </div>
            {zoomFrame.note && <p className="text-sm text-on-surface-variant">{zoomFrame.note}</p>}
          </div>
        )}
      </Modal>
    </section>
  );
}

function ScreeningResponses({ interview }: { interview: InterviewReviewData }) {
  const responses = interview.screeningAnswers ?? [];
  const answeredCount = responses.filter(response => response.answered).length;
  const [previewFile, setPreviewFile] = useState<ScreeningAnswer | null>(null);
  const isPdf =
    previewFile?.fileMime === 'application/pdf' ||
    previewFile?.fileName?.toLowerCase().endsWith('.pdf');

  return (
    <section className="border border-outline-variant bg-surface">
      <div className="border-b border-outline-variant px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <ClipboardList size={16} className="shrink-0 text-primary-fixed-dim" />
          <h2 className="label-mono text-on-surface">Screening Form</h2>
        </div>
        {responses.length > 0 && (
          <span className="shrink-0 border border-outline-variant px-2 py-1 label-mono text-on-surface-variant">
            {answeredCount}/{responses.length} answered
          </span>
        )}
      </div>
      {responses.length > 0 ? (
        <div className="divide-y divide-outline-variant">
          {responses.map((response, index) => (
            <div
              key={response.key}
              className="grid grid-cols-1 lg:grid-cols-[minmax(180px,0.38fr)_1fr] gap-4 px-4 py-4"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="label-mono text-primary-fixed-dim">
                    Q{String(index + 1).padStart(2, '0')}
                  </span>
                  <span
                    className={cn(
                      'border px-2 py-0.5 label-mono',
                      response.required
                        ? 'border-primary-container text-primary-fixed-dim'
                        : 'border-outline-variant text-on-surface-variant',
                    )}
                  >
                    {response.required ? 'Required' : 'Optional'}
                  </span>
                </div>
                <p className="mt-2 font-medium text-on-surface break-words">{response.label}</p>
              </div>
              <div
                className={cn(
                  'min-h-[56px] border px-3 py-2 text-sm leading-6 whitespace-pre-wrap break-words',
                  response.answered
                    ? 'border-outline-variant bg-surface-container-lowest text-on-surface'
                    : 'border-outline-variant bg-surface text-on-surface-variant',
                )}
              >
                {response.fieldType === 'file' && response.answered ? (
                  <button
                    type="button"
                    onClick={() => setPreviewFile(response)}
                    disabled={!response.fileUrl}
                    className="inline-flex max-w-full items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-primary-fixed-dim hover:border-primary-container hover:text-on-surface transition-colors duration-150 disabled:cursor-not-allowed disabled:text-on-surface-variant disabled:opacity-70"
                  >
                    <Eye size={14} className="shrink-0" />
                    <span className="truncate">
                      {response.fileName ?? response.answer ?? 'View file'}
                    </span>
                  </button>
                ) : (
                  response.answer ?? 'Not answered'
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-8 text-center label-mono text-on-surface-variant">
          No screening responses were captured for this interview.
        </div>
      )}
      <Modal
        open={!!previewFile}
        onClose={() => setPreviewFile(null)}
        title={previewFile?.fileName ?? previewFile?.label ?? 'Uploaded file'}
        size="xl"
      >
        {previewFile?.fileUrl ? (
          <div className="space-y-4">
            {isPdf ? (
              <iframe
                src={previewFile.fileUrl}
                title={previewFile.fileName ?? previewFile.label}
                className="h-[70vh] w-full border border-outline-variant bg-surface-container-lowest"
              />
            ) : (
              <div className="border border-outline-variant bg-surface-container-lowest p-8 text-center">
                <FileText size={32} className="mx-auto text-primary-fixed-dim" />
                <p className="mt-3 font-medium text-on-surface">
                  {previewFile.fileName ?? 'Uploaded document'}
                </p>
                <p className="mt-2 text-sm text-on-surface-variant">
                  This file type opens in the browser or your document viewer.
                </p>
              </div>
            )}
            <a
              href={previewFile.fileUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 border border-outline-variant px-3 py-1.5 label-mono text-primary-fixed-dim hover:border-primary-container hover:text-on-surface transition-colors duration-150"
            >
              <ExternalLink size={14} />
              Open file
            </a>
          </div>
        ) : (
          <div className="p-8 text-center label-mono text-on-surface-variant">
            File preview is unavailable. Refresh the page to request a new file link.
          </div>
        )}
      </Modal>
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
  const { data: interview, isLoading, isError } = useConsoleReview(interviewId);
  const reviewMutation = useReviewDecision(interviewId);
  const { toast } = useToast();
  const transcriptRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [currentSeconds, setCurrentSeconds] = useState(0);
  const [localDecision, setLocalDecision] = useState<ReviewDecision | null>(null);
  const decision = localDecision ?? interview?.reviewDecision ?? null;

  const recommendedDecision = useMemo<ReviewDecision | null>(() => {
    if (!interview) return null;
    return interview.recommendation;
  }, [interview]);

  // Active row = the last turn that started at or before the playhead, so the
  // highlight follows playback and any seek (waveform, skip, transcript click).
  const activeTranscriptId = useMemo(() => {
    const transcript = interview?.transcript;
    if (!transcript?.length) return '';
    const active = transcript.filter(t => t.seconds <= currentSeconds).at(-1) ?? transcript[0];
    return active.id;
  }, [interview?.transcript, currentSeconds]);

  if (!interview) {
    return (
      <ConsoleLayout>
        <div className="p-8 max-w-3xl">
          <Link to="/console/interviews" className="inline-flex items-center gap-2 label-mono text-on-surface-variant hover:text-primary-fixed-dim">
            <ArrowLeft size={16} />
            Back to interviews
          </Link>
          <div className="mt-8 border border-outline-variant bg-surface p-8">
            {isLoading && !isError ? (
              <p className="label-mono text-on-surface-variant">Loading interview review…</p>
            ) : (
              <>
                <p className="label-mono text-error">Interview not found</p>
                <p className="mt-2 text-on-surface-variant">The requested interview review does not exist in the current dataset.</p>
              </>
            )}
          </div>
        </div>
      </ConsoleLayout>
    );
  }

  const markDecision = (action: ReviewDecision) => {
    if (interview.scoringStatus !== 'Done') {
      toast('Scoring is still in progress — decisions unlock once the report is ready.', 'info');
      return;
    }
    setLocalDecision(action);
    reviewMutation.mutate(
      { decision: action },
      {
        onError: err => {
          setLocalDecision(null);
          const message =
            (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
            'Saving the decision failed. Please try again.';
          toast(message, 'error');
        },
        onSuccess: () => toast(`Review marked ${action}.`, 'success'),
      },
    );
  };

  // Both jumps just move the playhead — the audio element follows via drift
  // correction and the active row is derived from currentSeconds.
  const jumpToTranscript = (turn: TranscriptTurn) => {
    setCurrentSeconds(turn.seconds);
  };

  const jumpToTimeline = (seconds: number) => {
    setCurrentSeconds(seconds);
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
            <div className="mt-2 flex items-start gap-4">
              <CandidatePhoto
                url={interview.selfieUrl}
                alt={`${interview.candidateName} — verification photo`}
              />
              <div>
                <h1 className="font-display text-headline-lg text-on-surface tracking-tight">{interview.candidateName}</h1>
                {interview.candidateEmail && (
                  <div className="mt-1 flex items-center gap-2">
                    <p className="text-on-surface-variant break-all">{interview.candidateEmail}</p>
                    <CopyButton
                      text={interview.candidateEmail}
                      label={`Copy ${interview.candidateEmail}`}
                    />
                  </div>
                )}
                <p className="label-mono text-on-surface-variant mt-1">
                  {interview.code.toUpperCase()} / {interview.requisitionId} / {interview.requisitionTitle}
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(['Shortlist', 'Hold', 'Reject'] as const).map(action => {
              const color = DECISION_BUTTON_CLASS[action];
              return (
                <button
                  key={action}
                  type="button"
                  onClick={() => markDecision(action)}
                  disabled={reviewMutation.isPending}
                  className={cn(
                    'h-10 px-4 border label-mono transition-colors duration-150 flex items-center gap-2',
                    decision === action ? color.active : color.idle,
                    reviewMutation.isPending && 'opacity-60 cursor-wait',
                  )}
                >
                  {action === 'Reject' ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
                  {action}
                </button>
              );
            })}
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
                  {interview.scoringStatus === 'Done' && (
                    <span className="inline-flex border border-primary-container px-2 py-1 label-mono text-primary-fixed-dim">
                      AI recommends {recommendedDecision}
                    </span>
                  )}
                  {decision && (
                    <span className="inline-flex border border-outline-variant px-2 py-1 label-mono text-on-surface-variant">
                      Review marked {decision}
                    </span>
                  )}
                </div>
                <p className="mt-4 text-body-md text-on-surface max-w-3xl">{interview.assessmentSummary}</p>
                {interview.scoringStatus === 'Done' && interview.assessmentSummary && (
                  <div className="mt-3">
                    <CopyTextButton text={interview.assessmentSummary} label="Copy summary" />
                  </div>
                )}
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
            <EvidenceMetric
              label="Candidate"
              value={interview.candidateName}
              sub={interview.candidateEmail}
              copyableSub
            />
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
            <ScreeningResponses interview={interview} />
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
                {interview.reviewTrail.length > 0 ? (
                  interview.reviewTrail.map((entry, i) => (
                    <div key={`${entry.action}-${i}`} className="flex items-start justify-between gap-3">
                      <p>
                        <span className="text-on-surface">{entry.actor}</span> · {entry.action}
                        {entry.detail ? ` — ${entry.detail}` : ''}
                      </p>
                      <span className="label-mono shrink-0">
                        {dateTimeFormatter.format(new Date(entry.at))}
                      </span>
                    </div>
                  ))
                ) : (
                  <p>No review activity yet — scoring events will appear here.</p>
                )}
              </div>
            </section>
          </div>
        </div>
      </div>
    </ConsoleLayout>
  );
}
