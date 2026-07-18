/**
 * /apply/:applicationId/interview — Live AI voice interview room.
 *
 * Connects to the LiveKit room minted by POST /join (JoinOut), publishes the
 * candidate mic, plays the agent's TTS audio, and renders live captions, a
 * countdown timer, and interview state from the `kandidly` data channel
 * (see web/src/lib/interviewChannel.ts, mirroring agent/datamsg.py).
 *
 * Layout is a CSS grid (.interview-grid in index.css): header / stage /
 * transcript / controls stacked on mobile, with the transcript as a
 * full-height right rail on desktop. The stage renders both voices from the
 * real audio via Web Audio analysers (components/voice.tsx): the agent as a
 * level-driven orb, the candidate as an FFT equalizer strip. Speaking status
 * is derived from those levels, not caption timing.
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
import { Mic, MicOff, PhoneOff, Settings2, Volume2, WifiOff, AlertTriangle, CameraOff, X } from 'lucide-react';
import { candidateApi } from '../../lib/api';
import { Button, Select } from '../../components/ui';
import { AgentOrb, EqualizerBars } from '../../components/voice';
import type { JoinOut } from '../../lib/types';
import {
  decodeInterviewMessage,
  formatRemaining,
  type InterviewMessage,
} from '../../lib/interviewChannel';
import { createVizEngine, type VizEngine, type VoiceAnalyser } from '../../lib/audioViz';
import { getPreferredDevice, setPreferredDevice } from '../../lib/devicePrefs';
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

type ActiveVoice = 'kandidly' | 'candidate' | null;

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

  // Mid-interview device switching (mic republishes via LiveKit; camera
  // repoints the proctoring snapshot loop).
  const [devicesOpen, setDevicesOpen] = useState(false);
  const [micDevices, setMicDevices] = useState<MediaDeviceInfo[]>([]);
  const [camDevices, setCamDevices] = useState<MediaDeviceInfo[]>([]);
  const [activeMicId, setActiveMicId] = useState('');
  const [activeCamId, setActiveCamId] = useState('');
  const [switchError, setSwitchError] = useState<string | null>(null);

  // Audio-level analysers driving the orb / equalizer / speaking status.
  const [agentAnalyser, setAgentAnalyser] = useState<VoiceAnalyser | null>(null);
  const [micAnalyser, setMicAnalyser] = useState<VoiceAnalyser | null>(null);
  const [activeVoice, setActiveVoice] = useState<ActiveVoice>(null);

  const roomRef = useRef<Room | null>(null);
  const vizRef = useRef<VizEngine | null>(null);
  const audioElsRef = useRef<HTMLAudioElement[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
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
    const viz = createVizEngine();
    vizRef.current = viz;
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
      if (track.mediaStreamTrack) {
        // Mix the agent's audio into the interview recording (best-effort).
        recorderRef.current?.addTrack(track.mediaStreamTrack);
        // Drive the orb from the agent's real output level.
        const analyser = viz.attach(track.mediaStreamTrack);
        setAgentAnalyser(prev => {
          prev?.dispose();
          return analyser;
        });
      }
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
        // Use the mic chosen in the lobby device check when there is one;
        // `ideal` lets the browser fall back if that device is gone.
        const preferredMic = getPreferredDevice('audioinput');
        await room.localParticipant.setMicrophoneEnabled(
          true,
          preferredMic ? { deviceId: { ideal: preferredMic } } : undefined,
        );
        if (cancelled) return;
        setMicEnabled(true);
        setNeedsAudioGesture(!room.canPlaybackAudio);
        setPhase('live');

        const micTrack = room.localParticipant.getTrackPublication(Track.Source.Microphone)
          ?.track?.mediaStreamTrack;
        if (micTrack) setMicAnalyser(viz.attach(micTrack));

        // Recording + proctoring are best-effort side channels: any failure
        // here must never break the live call.
        const interviewId = interviewIdFromRoom(joinData.room_name);
        if (interviewId) {
          try {
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
          // Snapshot proctoring is per-requisition; when disabled, never ask
          // for the camera. Missing field (stale router state) means enabled.
          if (!snapshotsRef.current && joinData.proctoring?.enabled !== false) {
            snapshotsRef.current = startSnapshotLoop(interviewId, {
              intervalS: joinData.proctoring?.snapshot_interval_s ?? 10,
              deviceId: getPreferredDevice('videoinput'),
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
      viz.dispose();
      vizRef.current = null;
      setAgentAnalyser(null);
      setMicAnalyser(null);
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

  // ── Who is speaking, from real audio levels (not caption timing) ──────────
  useEffect(() => {
    if (phase !== 'live') return;
    let last: ActiveVoice = null;
    let lastAt = 0;
    const id = setInterval(() => {
      const agent = agentAnalyser?.readLevel() ?? 0;
      const cand = micEnabled ? micAnalyser?.readLevel() ?? 0 : 0;
      const now = Date.now();
      let next: ActiveVoice = null;
      if (agent > 0.1 && agent >= cand) next = 'kandidly';
      else if (cand > 0.1) next = 'candidate';
      if (next) {
        last = next;
        lastAt = now;
      } else if (now - lastAt < 1200) {
        next = last; // short hang so the label doesn't flicker between words
      }
      setActiveVoice(next);
    }, 160);
    return () => clearInterval(id);
  }, [phase, agentAnalyser, micAnalyser, micEnabled]);

  // Stream the transcript: stay pinned to the newest line unless the
  // candidate has scrolled up to re-read something.
  const handleTranscriptScroll = useCallback(() => {
    const el = transcriptRef.current;
    if (el) stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);
  useEffect(() => {
    const el = transcriptRef.current;
    if (el && stickToBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [finals, partial]);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !micEnabled;
    setMicEnabled(next);
    try {
      const preferredMic = getPreferredDevice('audioinput');
      await room.localParticipant.setMicrophoneEnabled(
        next,
        next && preferredMic ? { deviceId: { ideal: preferredMic } } : undefined,
      );
    } catch {
      setMicEnabled(!next); // revert on failure
    }
  }, [micEnabled]);

  // ── Mid-interview device switching ────────────────────────────────────────
  const openDevices = useCallback(async () => {
    setSwitchError(null);
    setDevicesOpen(true);
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setMicDevices(all.filter(d => d.kind === 'audioinput' && d.deviceId));
      setCamDevices(all.filter(d => d.kind === 'videoinput' && d.deviceId));
    } catch {
      /* the pickers just stay empty */
    }
    const room = roomRef.current;
    setActiveMicId(
      room?.getActiveDevice('audioinput') ??
        room?.localParticipant
          .getTrackPublication(Track.Source.Microphone)
          ?.track?.mediaStreamTrack?.getSettings().deviceId ??
        getPreferredDevice('audioinput') ??
        '',
    );
    setActiveCamId(
      snapshotsRef.current?.getDeviceId() ?? getPreferredDevice('videoinput') ?? '',
    );
  }, []);

  const switchMic = useCallback(async (deviceId: string) => {
    const room = roomRef.current;
    if (!room || !deviceId) return;
    setSwitchError(null);
    try {
      // `exact` so an explicit pick can't silently fall back to the old mic.
      const ok = await room.switchActiveDevice('audioinput', deviceId, true);
      if (!ok) throw new Error('switch rejected');
      setActiveMicId(deviceId);
      setPreferredDevice('audioinput', deviceId);
      // The published track was restarted on the new device — repoint the
      // equalizer analyser and mix the new track into the recording.
      const track = room.localParticipant
        .getTrackPublication(Track.Source.Microphone)
        ?.track?.mediaStreamTrack;
      if (track && vizRef.current) {
        const analyser = vizRef.current.attach(track);
        setMicAnalyser(prev => {
          prev?.dispose();
          return analyser;
        });
        recorderRef.current?.addTrack(track);
      }
    } catch {
      setSwitchError("Couldn't switch microphone — still using the previous one.");
    }
  }, []);

  const switchCam = useCallback(async (deviceId: string) => {
    if (!deviceId) return;
    setSwitchError(null);
    const ok = await snapshotsRef.current?.setDevice(deviceId);
    if (ok) {
      setActiveCamId(deviceId);
      setPreferredDevice('videoinput', deviceId);
      setCameraBanner(false); // a working camera clears the denial notice
    } else {
      setSwitchError("Couldn't switch camera — still using the previous one.");
    }
  }, []);

  const enableAudio = useCallback(async () => {
    try {
      await roomRef.current?.startAudio();
      vizRef.current?.resume();
      audioElsRef.current.forEach(el => el.play?.().catch(() => {}));
      setNeedsAudioGesture(false);
    } catch {
      /* keep the prompt up; user can retry */
    }
  }, []);

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
        ? 'Kandidly is getting ready'
        : phase === 'connecting'
          ? 'Connecting you to the interview'
          : 'Preparing your interview';
    return (
      <InterviewShell>
        <div className="flex flex-col items-center gap-8 py-8">
          <AgentOrb analyser={null} size={128} />
          <p className="label-mono blink" style={{ color: 'var(--text-muted)' }}>
            {label}…
          </p>
        </div>
      </InterviewShell>
    );
  }

  // ── Live room ─────────────────────────────────────────────────────────────
  // The agent's audio is played via elements appended to <body> in
  // handleTrackSubscribed (see above), so there's no <audio> in this tree.
  return (
    <div className="interview-grid" style={{ background: 'var(--background)' }}>
      {/* Header + interrupt banners */}
      <div style={{ gridArea: 'header' }} className="border-b" >
        <header className="flex items-center justify-between px-4 sm:px-6 h-14">
          <div className="flex items-center gap-3">
            <div
              className="size-7 flex items-center justify-center font-display font-bold text-sm"
              style={{ background: 'var(--accent)', color: 'var(--on-primary-container)' }}
            >
              K
            </div>
            <span className="label-mono" style={{ color: 'var(--text-secondary)' }}>
              Live interview
            </span>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden sm:flex items-center gap-1.5 label-mono" style={{ color: 'var(--error)' }}>
              <span className="size-1.5 rounded-full blink" style={{ background: 'var(--error)' }} />
              Rec
            </span>
            {timer && (
              <span
                className="font-mono text-sm font-medium tabular-nums"
                style={{ color: isWrapping ? 'var(--amber-chip-text)' : 'var(--text-primary)' }}
              >
                {isWrapping && (
                  <span className="text-2xs uppercase tracking-[0.15em] mr-2">Wrapping up</span>
                )}
                {formatRemaining(timer.remaining_s)}
              </span>
            )}
          </div>
        </header>

        {needsAudioGesture && (
          <button
            onClick={enableAudio}
            className="flex items-center justify-center gap-2 py-2.5 text-sm font-medium w-full"
            style={{ background: 'var(--accent-muted)', color: 'var(--primary)' }}
          >
            <Volume2 size={15} />
            Tap to enable interview audio
          </button>
        )}

        {cameraBanner && (
          <div
            className="flex items-center justify-center gap-2 py-2.5 px-4 text-sm w-full"
            style={{ background: 'var(--amber-chip-bg)', color: 'var(--amber-chip-text)' }}
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
      </div>

      {/* Stage: agent orb + speaking status + candidate equalizer */}
      <section
        style={{ gridArea: 'stage' }}
        className="flex flex-col items-center justify-center gap-5 lg:gap-8 px-4 py-6 lg:py-10 min-h-0"
      >
        <AgentOrb analyser={agentAnalyser} className="size-36 sm:size-40 lg:size-48 shrink-0" />
        <p
          className="label-mono text-center"
          style={{
            color: activeVoice === 'kandidly' ? 'var(--primary)' : 'var(--text-muted)',
          }}
        >
          {activeVoice === 'kandidly'
            ? 'Kandidly is speaking'
            : activeVoice === 'candidate'
              ? 'Listening to you'
              : 'Interview in progress'}
        </p>
        <div className="w-full max-w-md">
          <div className="flex items-center justify-between mb-2">
            <span
              className="font-mono text-2xs font-medium uppercase tracking-[0.15em]"
              style={{
                color: activeVoice === 'candidate' ? 'var(--primary)' : 'var(--text-muted)',
              }}
            >
              You
            </span>
            {!micEnabled && (
              <span
                className="font-mono text-2xs font-medium uppercase tracking-[0.15em]"
                style={{ color: 'var(--error)' }}
              >
                Muted
              </span>
            )}
          </div>
          <EqualizerBars analyser={micEnabled ? micAnalyser : null} height={44} />
        </div>
      </section>

      {/* Transcript rail */}
      <aside
        style={{ gridArea: 'transcript', background: 'var(--surface-container-lowest)' }}
        className="min-h-0 flex flex-col border-t lg:border-t-0 lg:border-l"
      >
        <div className="flex items-center justify-between px-4 lg:px-5 py-3 border-b shrink-0">
          <span className="label-mono" style={{ color: 'var(--text-muted)' }}>
            Transcript
          </span>
          <span className="font-mono text-2xs tabular-nums" style={{ color: 'var(--text-muted)' }}>
            {finals.length} {finals.length === 1 ? 'turn' : 'turns'}
          </span>
        </div>
        <div
          ref={transcriptRef}
          onScroll={handleTranscriptScroll}
          aria-live="polite"
          className="flex-1 min-h-0 overflow-y-auto px-4 lg:px-5 py-4 space-y-4"
        >
          {finals.length === 0 && !partial && (
            <p className="font-mono text-2xs uppercase tracking-[0.15em] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Captions appear here as the conversation begins.
            </p>
          )}
          {finals.map(c => (
            <CaptionLine key={c.seq} speaker={c.speaker} text={c.text} />
          ))}
          {partial && <CaptionLine speaker={partial.speaker} text={partial.text} streaming />}
        </div>
      </aside>

      {/* Controls */}
      <footer
        style={{ gridArea: 'controls', paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom))' }}
        className="flex items-center justify-center gap-3 border-t px-4 pt-3"
      >
        <button
          onClick={toggleMic}
          aria-label={micEnabled ? 'Mute microphone' : 'Unmute microphone'}
          aria-pressed={!micEnabled}
          className="h-12 flex-1 sm:flex-none sm:w-40 flex items-center justify-center gap-2 border font-mono text-xs font-medium uppercase tracking-[0.1em] transition-colors duration-150"
          style={
            micEnabled
              ? { borderColor: 'var(--border)', background: 'var(--surface)', color: 'var(--text-primary)' }
              : { borderColor: 'var(--error)', background: 'var(--red-chip-bg)', color: 'var(--error)' }
          }
        >
          {micEnabled ? <Mic size={16} /> : <MicOff size={16} />}
          {micEnabled ? 'Mic on' : 'Mic off'}
        </button>
        <button
          onClick={() => void openDevices()}
          aria-label="Change microphone or camera"
          aria-expanded={devicesOpen}
          className="h-12 w-12 sm:w-auto sm:px-4 shrink-0 flex items-center justify-center gap-2 border font-mono text-xs font-medium uppercase tracking-[0.1em] transition-colors duration-150"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)', color: 'var(--text-primary)' }}
        >
          <Settings2 size={16} />
          <span className="hidden sm:inline">Devices</span>
        </button>
        <button
          onClick={leave}
          aria-label="End interview"
          className="h-12 flex-1 sm:flex-none sm:w-48 flex items-center justify-center gap-2 font-mono text-xs font-medium uppercase tracking-[0.1em] transition-colors duration-150"
          style={{ background: 'var(--error-container)', color: 'var(--on-error-container)' }}
        >
          <PhoneOff size={16} />
          End interview
        </button>
      </footer>

      {/* Device switcher — bottom sheet on mobile, centered card on desktop.
          Mic changes republish through LiveKit; camera changes repoint the
          proctoring snapshot loop (hidden when proctoring is off). */}
      {devicesOpen && (
        <div
          className="fixed inset-0 z-40 flex items-end sm:items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.55)' }}
          onClick={() => setDevicesOpen(false)}
        >
          <div
            role="dialog"
            aria-label="Device settings"
            className="w-full max-w-md border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
            onClick={e => e.stopPropagation()}
          >
            <header className="flex items-center justify-between px-4 py-3 border-b">
              <span className="flex items-center gap-2 label-mono" style={{ color: 'var(--text-secondary)' }}>
                <Settings2 size={14} />
                Devices
              </span>
              <button
                onClick={() => setDevicesOpen(false)}
                aria-label="Close device settings"
                className="opacity-70 hover:opacity-100"
                style={{ color: 'var(--text-secondary)' }}
              >
                <X size={16} />
              </button>
            </header>
            <div className="p-4 space-y-4">
              <Select
                label="Microphone"
                value={activeMicId}
                onChange={e => void switchMic(e.target.value)}
                options={micDevices.map((d, i) => ({
                  value: d.deviceId,
                  label: d.label || `Microphone ${i + 1}`,
                }))}
              />
              {joinData?.proctoring?.enabled !== false && (
                <Select
                  label="Camera"
                  value={activeCamId}
                  onChange={e => void switchCam(e.target.value)}
                  options={camDevices.map((d, i) => ({
                    value: d.deviceId,
                    label: d.label || `Camera ${i + 1}`,
                  }))}
                />
              )}
              {switchError && (
                <p className="text-xs" style={{ color: 'var(--amber-chip-text)' }}>
                  {switchError}
                </p>
              )}
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Changes apply immediately — the interview keeps going.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CaptionLine({ speaker, text, streaming }: { speaker: string; text: string; streaming?: boolean }) {
  const isAgent = speaker === 'kandidly';
  return (
    <div className="space-y-1">
      <span
        className="font-mono text-2xs font-medium uppercase tracking-[0.15em]"
        style={{ color: isAgent ? 'var(--primary)' : 'var(--text-muted)' }}
      >
        {speakerLabel(speaker)}
      </span>
      <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
        {text}
        {streaming && <span className="caption-caret" />}
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
            className="size-8 flex items-center justify-center font-display font-bold text-sm"
            style={{ background: 'var(--accent)', color: 'var(--on-primary-container)' }}
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
  const border = tone === 'warn' ? 'rgba(245,158,11,0.2)' : 'rgba(46,91,255,0.3)';
  const bg = tone === 'warn' ? 'rgba(245,158,11,0.05)' : 'rgba(46,91,255,0.05)';
  return (
    <div className="border p-6 text-center space-y-3 w-full" style={{ borderColor: border, background: bg }}>
      <div className="flex justify-center">{icon}</div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{title}</p>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{body}</p>
    </div>
  );
}
