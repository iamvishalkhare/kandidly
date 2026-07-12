/**
 * /apply/:applicationId/interview — Live AI voice interview room.
 *
 * Connects to the LiveKit room minted by POST /join (JoinOut), publishes the
 * candidate mic, plays the agent's TTS audio, and renders live captions, a
 * countdown timer, and interview state from the `kandidly` data channel
 * (see web/src/lib/interviewChannel.ts, mirroring agent/datamsg.py).
 *
 * The JoinOut is normally handed over from the lobby via router state; on a
 * refresh or direct navigation we re-call join (an idempotent rejoin once the
 * application is in_interview).
 */

import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
  type RemoteTrackPublication,
  type RemoteParticipant,
} from 'livekit-client';
import { Mic, MicOff, PhoneOff, Volume2, WifiOff, AlertTriangle, CameraOff, X } from 'lucide-react';
import { candidateApi, publicApi } from '../../lib/api';
import { Button, Spinner } from '../../components/ui';
import { cn } from '../../lib/utils';
import type { JoinOut } from '../../lib/types';
import {
  decodeInterviewMessage,
  formatRemaining,
  type InterviewMessage,
} from '../../lib/interviewChannel';
import { createInterviewRecorder, type InterviewRecorder } from '../../lib/useInterviewRecorder';
import { startSnapshotLoop, type SnapshotLoop } from '../../lib/useProctorSnapshots';

/** Interview id from the LiveKit room name (`kndl-{interview_id}`) — the
 * JoinOut carries no explicit id; this mirrors the agent's convention. */
function interviewIdFromRoom(roomName: string | undefined): string | null {
  return roomName?.startsWith('kndl-') ? roomName.slice('kndl-'.length) : null;
}

type Phase =
  | 'acquiring'   // fetching a join token
  | 'not_ready'   // 202 from join — agent/plan not ready, polling
  | 'connecting'  // have token, connecting to the room
  | 'live'        // connected
  | 'ended'       // interview finished (navigating away)
  | 'unavailable' // LiveKit not configured in this environment
  | 'error';      // unexpected failure

interface Caption {
  seq: number;
  speaker: string;
  text: string;
}

function speakerLabel(speaker: string): string {
  if (speaker === 'kandidly') return 'Kandidly';
  if (speaker === 'candidate') return 'You';
  return speaker || '—';
}

export default function CandidateInterview() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const initialJoin = (location.state as JoinOut | null) ?? null;
  const [joinData, setJoinData] = useState<JoinOut | null>(initialJoin);
  const [phase, setPhase] = useState<Phase>(initialJoin ? 'connecting' : 'acquiring');

  // Live interview state driven by the data channel.
  const [timer, setTimer] = useState<{ remaining_s: number; phase: string } | null>(null);
  const [finals, setFinals] = useState<Caption[]>([]);
  const [partial, setPartial] = useState<{ speaker: string; text: string } | null>(null);
  const [micEnabled, setMicEnabled] = useState(true);
  const [needsAudioGesture, setNeedsAudioGesture] = useState(false);
  const [cameraBanner, setCameraBanner] = useState(false);

  const roomRef = useRef<Room | null>(null);
  const audioElsRef = useRef<HTMLAudioElement[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<InterviewRecorder | null>(null);
  const snapshotsRef = useRef<SnapshotLoop | null>(null);

  const leave = useCallback(() => {
    // Kick off the recording flush before navigating; the SPA keeps the JS
    // context alive so pending chunk uploads and /recording/complete finish.
    void recorderRef.current?.stop();
    recorderRef.current = null;
    snapshotsRef.current?.stop();
    snapshotsRef.current = null;
    setPhase('ended');
    navigate(`/apply/${applicationId}/done?from=interview`, { replace: true });
  }, [applicationId, navigate]);

  // ── Acquire a join token if we didn't get one from the lobby ──────────────
  useEffect(() => {
    if (joinData) return; // already have it (router state or a prior attempt)
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const attempt = async () => {
      try {
        const data = await candidateApi.join(applicationId!);
        if (cancelled) return;
        setJoinData(data);
        setPhase('connecting');
      } catch (err) {
        if (cancelled) return;
        const e = err as { response?: { status?: number; data?: { code?: string; retry_after_s?: number } } };
        const status = e?.response?.status;
        if (status === 202) {
          setPhase('not_ready');
          const retry = e.response?.data?.retry_after_s ?? 3;
          pollTimer = setTimeout(attempt, retry * 1000);
        } else if (status === 500 || e?.response?.data?.code === 'internal_error') {
          setPhase('unavailable');
        } else {
          setPhase('error');
        }
      }
    };
    attempt();

    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [applicationId, joinData]);

  // ── Connect to the LiveKit room once we have a token ──────────────────────
  useEffect(() => {
    if (!joinData) return;
    const room = new Room();
    roomRef.current = room;
    let cancelled = false;

    const handleData = (payload: Uint8Array) => {
      const msg = decodeInterviewMessage(payload);
      if (msg) applyMessage(msg);
    };
    const applyMessage = (msg: InterviewMessage) => {
      switch (msg.type) {
        case 'caption.partial':
          setPartial({ speaker: msg.speaker, text: msg.text });
          break;
        case 'caption.final':
          setFinals(prev =>
            prev.some(c => c.seq === msg.turn_seq)
              ? prev
              : [...prev, { seq: msg.turn_seq, speaker: msg.speaker, text: msg.text }].slice(-100),
          );
          setPartial(null);
          break;
        case 'control.timer':
          setTimer({ remaining_s: msg.remaining_s, phase: msg.phase });
          break;
        case 'control.state':
          if (msg.status === 'ended' || msg.status === 'finalized') leave();
          break;
        default:
          break;
      }
    };

    const handleTrackSubscribed = (
      track: RemoteTrack,
      _pub: RemoteTrackPublication,
      _participant: RemoteParticipant,
    ) => {
      if (track.kind !== Track.Kind.Audio) return;
      // Let livekit create the media element and append it to the DOM ourselves,
      // rather than binding to a React-rendered <audio> ref that may not be
      // mounted yet when the agent's track arrives (that race = silent agent).
      const el = track.attach() as HTMLAudioElement;
      el.autoplay = true;
      el.style.display = 'none';
      document.body.appendChild(el);
      audioElsRef.current.push(el);
      // Browsers may block autoplay without a gesture — prompt if so.
      el.play?.().catch(() => setNeedsAudioGesture(true));
      // Mix the agent's audio into the interview recording (best-effort).
      if (track.mediaStreamTrack) recorderRef.current?.addTrack(track.mediaStreamTrack);
    };

    const handlePlaybackChanged = () => {
      setNeedsAudioGesture(!room.canPlaybackAudio);
    };

    room
      .on(RoomEvent.DataReceived, handleData)
      .on(RoomEvent.TrackSubscribed, handleTrackSubscribed)
      .on(RoomEvent.AudioPlaybackStatusChanged, handlePlaybackChanged)
      .on(RoomEvent.Disconnected, leave);

    (async () => {
      try {
        await room.connect(joinData.livekit_url, joinData.token);
        if (cancelled) return;
        await room.localParticipant.setMicrophoneEnabled(true);
        if (cancelled) return;
        setMicEnabled(true);
        setNeedsAudioGesture(!room.canPlaybackAudio);
        setPhase('live');

        // Recording + proctoring are best-effort side channels: any failure
        // here must never break the live call.
        const interviewId = interviewIdFromRoom(joinData.room_name);
        if (interviewId) {
          try {
            const micTrack = room.localParticipant.getTrackPublication(Track.Source.Microphone)
              ?.track?.mediaStreamTrack;
            if (micTrack && !recorderRef.current) {
              recorderRef.current = createInterviewRecorder(interviewId);
              recorderRef.current?.addTrack(micTrack);
              // The agent's track may have arrived before the recorder existed.
              audioElsRef.current.forEach(el => {
                const stream = el.srcObject as MediaStream | null;
                stream?.getAudioTracks().forEach(t => recorderRef.current?.addTrack(t));
              });
            }
          } catch {
            /* recording is best-effort */
          }
          if (!snapshotsRef.current) {
            const cfg = await publicApi.getConfig().catch(() => null);
            if (cancelled) return;
            snapshotsRef.current = startSnapshotLoop(interviewId, {
              intervalS: cfg?.snapshot_interval_s ?? 10,
              onCameraDenied: () => setCameraBanner(true),
            });
          }
        }
      } catch {
        if (!cancelled) setPhase('error');
      }
    })();

    return () => {
      cancelled = true;
      room.removeAllListeners();
      room.disconnect();
      roomRef.current = null;
      void recorderRef.current?.stop();
      recorderRef.current = null;
      snapshotsRef.current?.stop();
      snapshotsRef.current = null;
      audioElsRef.current.forEach(el => {
        el.srcObject = null;
        el.remove();
      });
      audioElsRef.current = [];
    };
  }, [joinData, leave]);

  // Auto-scroll the transcript as new lines arrive.
  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [finals, partial]);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !micEnabled;
    setMicEnabled(next);
    try {
      await room.localParticipant.setMicrophoneEnabled(next);
    } catch {
      setMicEnabled(!next); // revert on failure
    }
  }, [micEnabled]);

  const enableAudio = useCallback(async () => {
    try {
      await roomRef.current?.startAudio();
      audioElsRef.current.forEach(el => el.play?.().catch(() => {}));
      setNeedsAudioGesture(false);
    } catch {
      /* keep the prompt up; user can retry */
    }
  }, []);

  const speaking = partial?.speaker ?? finals[finals.length - 1]?.speaker ?? null;
  const isWrapping = timer?.phase === 'wrap' || timer?.phase === 'wrap_up';

  // ── Non-live phases ───────────────────────────────────────────────────────
  if (phase === 'unavailable') {
    return (
      <InterviewShell>
        <StatusCard
          icon={<WifiOff size={24} style={{ color: 'var(--accent)' }} />}
          tone="accent"
          title="Voice interviews aren't enabled in this environment yet"
          body="This is a development environment without LiveKit configured. The rest of the candidate flow works; voice interviews will be available once infrastructure is set up."
        />
      </InterviewShell>
    );
  }

  if (phase === 'error') {
    return (
      <InterviewShell>
        <StatusCard
          icon={<AlertTriangle size={24} className="text-amber-400" />}
          tone="warn"
          title="We couldn't connect you to the interview"
          body="Something went wrong setting up the interview room. Please refresh to try again."
        />
        <Button variant="outline" size="lg" className="mt-4" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </InterviewShell>
    );
  }

  if (phase === 'acquiring' || phase === 'not_ready' || phase === 'connecting') {
    const label =
      phase === 'not_ready'
        ? 'Kandidly is getting ready…'
        : phase === 'connecting'
          ? 'Connecting you to the interview…'
          : 'Preparing your interview…';
    return (
      <InterviewShell>
        <div className="flex flex-col items-center gap-4 py-8">
          <Spinner size={28} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{label}</p>
        </div>
      </InterviewShell>
    );
  }

  // ── Live room ─────────────────────────────────────────────────────────────
  // The agent's audio is played via elements appended to <body> in
  // handleTrackSubscribed (see above), so there's no <audio> in this tree.
  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--background)' }}>
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 sm:px-6 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2.5">
          <div
            className="size-7 rounded-md flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            K
          </div>
          <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
            Live interview
          </span>
        </div>
        {timer && (
          <div className="flex items-center gap-2 text-sm tabular-nums" style={{ color: isWrapping ? '#fbbf24' : 'var(--text-secondary)' }}>
            {isWrapping && <span className="text-xs uppercase tracking-wide">Wrapping up</span>}
            <span className="font-medium">{formatRemaining(timer.remaining_s)}</span>
          </div>
        )}
      </header>

      {/* Audio-blocked banner */}
      {needsAudioGesture && (
        <button
          onClick={enableAudio}
          className="flex items-center justify-center gap-2 py-2.5 text-sm font-medium w-full"
          style={{ background: 'var(--accent-muted)', color: 'var(--accent)' }}
        >
          <Volume2 size={15} />
          Tap to enable interview audio
        </button>
      )}

      {/* Camera unavailable banner — proctoring degrades, interview continues */}
      {cameraBanner && (
        <div
          className="flex items-center justify-center gap-2 py-2.5 px-4 text-sm w-full"
          style={{ background: 'rgba(245,158,11,0.08)', color: '#fbbf24' }}
        >
          <CameraOff size={15} />
          <span>Camera unavailable — this session will be flagged for manual review.</span>
          <button
            onClick={() => setCameraBanner(false)}
            aria-label="Dismiss camera notice"
            className="ml-2 opacity-70 hover:opacity-100"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Center: agent orb + speaking status */}
      <div className="flex-1 flex flex-col items-center justify-center gap-6 px-4 py-8">
        <div className="relative flex items-center justify-center">
          <div
            className={cn(
              'size-28 rounded-full flex items-center justify-center transition-all duration-300',
              speaking === 'kandidly' && 'animate-pulse',
            )}
            style={{
              background: 'var(--accent-muted)',
              boxShadow: speaking === 'kandidly' ? '0 0 0 10px var(--accent-muted)' : 'none',
            }}
          >
            <div
              className="size-16 rounded-full flex items-center justify-center text-white font-bold text-xl"
              style={{ background: 'var(--accent)' }}
            >
              K
            </div>
          </div>
        </div>
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          {speaking === 'kandidly'
            ? 'Kandidly is speaking…'
            : speaking === 'candidate'
              ? 'Listening…'
              : 'Interview in progress'}
        </p>
      </div>

      {/* Transcript / captions */}
      <div
        ref={transcriptRef}
        className="max-h-48 overflow-y-auto px-4 sm:px-6 pb-4 space-y-3 w-full max-w-2xl mx-auto"
      >
        {finals.length === 0 && !partial && (
          <p className="text-center text-xs" style={{ color: 'var(--text-muted)' }}>
            Captions will appear here as the conversation begins.
          </p>
        )}
        {finals.map(c => (
          <CaptionLine key={c.seq} speaker={c.speaker} text={c.text} />
        ))}
        {partial && <CaptionLine speaker={partial.speaker} text={partial.text} dim />}
      </div>

      {/* Controls */}
      <footer className="flex items-center justify-center gap-4 px-4 py-6 border-t" style={{ borderColor: 'var(--border)' }}>
        <button
          onClick={toggleMic}
          aria-label={micEnabled ? 'Mute microphone' : 'Unmute microphone'}
          aria-pressed={!micEnabled}
          className="size-12 rounded-full flex items-center justify-center border transition-all duration-150"
          style={{
            borderColor: micEnabled ? 'var(--border)' : '#ef4444',
            background: micEnabled ? 'var(--surface)' : 'rgba(239,68,68,0.1)',
            color: micEnabled ? 'var(--text-primary)' : '#f87171',
          }}
        >
          {micEnabled ? <Mic size={18} /> : <MicOff size={18} />}
        </button>
        <button
          onClick={leave}
          aria-label="End interview"
          className="h-12 px-5 rounded-full flex items-center gap-2 text-sm font-medium text-white transition-all duration-150"
          style={{ background: '#ef4444' }}
        >
          <PhoneOff size={17} />
          End interview
        </button>
      </footer>
    </div>
  );
}

function CaptionLine({ speaker, text, dim }: { speaker: string; text: string; dim?: boolean }) {
  const isAgent = speaker === 'kandidly';
  return (
    <div className={cn('flex flex-col gap-0.5', dim && 'opacity-60')}>
      <span
        className="text-xs font-medium uppercase tracking-wide"
        style={{ color: isAgent ? 'var(--accent)' : 'var(--text-muted)' }}
      >
        {speakerLabel(speaker)}
      </span>
      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {text}
      </p>
    </div>
  );
}

function InterviewShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ background: 'var(--background)' }}>
      <div className="w-full max-w-sm flex flex-col items-center">
        <div className="flex justify-center mb-8">
          <div
            className="size-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            K
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

function StatusCard({
  icon,
  title,
  body,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  tone: 'accent' | 'warn';
}) {
  const border = tone === 'warn' ? 'rgba(245,158,11,0.2)' : 'rgba(139,124,246,0.2)';
  const bg = tone === 'warn' ? 'rgba(245,158,11,0.05)' : 'rgba(139,124,246,0.05)';
  return (
    <div className="rounded-xl border p-6 text-center space-y-3 w-full" style={{ borderColor: border, background: bg }}>
      <div className="flex justify-center">{icon}</div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{title}</p>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{body}</p>
    </div>
  );
}
