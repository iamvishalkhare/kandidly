/**
 * /apply/:applicationId/lobby — 3-step pre-interview flow.
 * Step 1: Consent (scroll text + 2 checkboxes)
 * Step 2: Devices (explicit mic/camera permission buttons + device pickers;
 *         the verification selfie is always required — the proctoring toggle
 *         only controls the periodic snapshot loop during the interview)
 * Step 3: Ready (what to expect + Join button)
 *
 * Device choices persist via lib/devicePrefs.ts; the interview room publishes
 * the chosen mic and points the proctoring snapshot loop at the chosen camera.
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, Mic, Video, WifiOff } from 'lucide-react';
import { candidateApi } from '../../lib/api';
import { Badge, Button, Select, Stepper, Spinner } from '../../components/ui';
import { AgentOrb, EqualizerBars } from '../../components/voice';
import { createVizEngine, type VizEngine, type VoiceAnalyser } from '../../lib/audioViz';
import { getPreferredDevice, setPreferredDevice } from '../../lib/devicePrefs';
import { cn } from '../../lib/utils';
import type { ApplicationOut, JoinOut } from '../../lib/types';

const CONSENT_VERSION = 'v1-2026-07';

// ─── Step 1: Consent ─────────────────────────────────────────────────────────

function ConsentStep({
  applicationId,
  proctoringEnabled,
  onDone,
}: {
  applicationId: string;
  proctoringEnabled: boolean;
  onDone: () => void;
}) {
  const [recordingAck, setRecordingAck] = useState(false);
  const [monitoringAck, setMonitoringAck] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      candidateApi.postConsent(applicationId, {
        consent_version: CONSENT_VERSION,
        recording_ack: true,
        monitoring_ack: true,
      }),
    onSuccess: onDone,
  });

  const canProceed = recordingAck && (monitoringAck || !proctoringEnabled);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          Before we begin
        </h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Please read and acknowledge the following.
        </p>
      </div>

      {/* Scrollable consent text */}
      <div
        className="rounded-lg border p-5 h-48 overflow-y-auto space-y-3 text-sm leading-relaxed"
        style={{ borderColor: 'var(--border)', background: 'var(--background)', color: 'var(--text-secondary)' }}
      >
        <p><strong style={{ color: 'var(--text-primary)' }}>Recording Consent</strong></p>
        <p>
          This interview will be recorded for evaluation purposes. The recording includes
          your audio and may be reviewed by the hiring team and our AI systems. You have the
          right to withdraw at any time before starting the interview.
        </p>
        {proctoringEnabled && (
          <>
            <p><strong style={{ color: 'var(--text-primary)' }}>Monitoring Disclosure</strong></p>
            <p>
              During the interview, our system may take periodic screenshots to verify your identity
              and ensure interview integrity. This data is stored securely and used only for
              evaluation and compliance purposes.
            </p>
          </>
        )}
        <p><strong style={{ color: 'var(--text-primary)' }}>Data Usage</strong></p>
        <p>
          Your interview data (transcript, recording, screenshots) will be retained for up to
          12 months and may be shared with the hiring organisation. It will not be sold to
          third parties. You may request deletion by contacting us.
        </p>
        <p><strong style={{ color: 'var(--text-primary)' }}>Consent Version:</strong> {CONSENT_VERSION}</p>
      </div>

      {/* Checkboxes */}
      <div className="space-y-4">
        <CheckItem
          checked={recordingAck}
          onChange={setRecordingAck}
          label="I consent to this interview being recorded and reviewed by AI systems and the hiring team."
        />
        {proctoringEnabled && (
          <CheckItem
            checked={monitoringAck}
            onChange={setMonitoringAck}
            label="I understand that periodic screenshots may be taken for identity verification."
          />
        )}
      </div>

      <Button
        variant="primary"
        size="lg"
        className="w-full"
        disabled={!canProceed}
        loading={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        I agree — continue
        <ArrowRight size={16} />
      </Button>
    </div>
  );
}

function CheckItem({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  // Real (visually-hidden) checkbox so the whole label is clickable and the
  // control is keyboard-focusable / toggleable with Space.
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className={cn(
          'mt-0.5 size-5 rounded shrink-0 border-2 flex items-center justify-center transition-all duration-150',
          'peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--accent)]',
          checked
            ? 'border-[var(--accent)] bg-[var(--accent)]'
            : 'border-[var(--border)] group-hover:border-[var(--accent)]'
        )}
      >
        {checked && <CheckCircle2 size={12} className="text-white" />}
      </span>
      <span className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{label}</span>
    </label>
  );
}

// ─── Step 2: Devices ─────────────────────────────────────────────────────────

type PermState = 'idle' | 'requesting' | 'granted' | 'denied';

function permBadge(state: PermState): { color: 'emerald' | 'red' | 'zinc'; label: string } {
  if (state === 'granted') return { color: 'emerald', label: 'Ready' };
  if (state === 'denied') return { color: 'red', label: 'Blocked' };
  return { color: 'zinc', label: 'Off' };
}

function DevicesStep({
  applicationId,
  proctoringEnabled,
  onDone,
}: {
  applicationId: string;
  proctoringEnabled: boolean;
  onDone: () => void;
}) {
  const vizRef = useRef<VizEngine | null>(null);

  // Microphone
  const micStreamRef = useRef<MediaStream | null>(null);
  const [micState, setMicState] = useState<PermState>('idle');
  const [micAnalyser, setMicAnalyser] = useState<VoiceAnalyser | null>(null);
  const [micDevices, setMicDevices] = useState<MediaDeviceInfo[]>([]);
  const [micId, setMicId] = useState('');

  // Camera + verification selfie (always required)
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const camStreamRef = useRef<MediaStream | null>(null);
  const [camState, setCamState] = useState<PermState>('idle');
  const [camStream, setCamStream] = useState<MediaStream | null>(null);
  const [camDevices, setCamDevices] = useState<MediaDeviceInfo[]>([]);
  const [camId, setCamId] = useState('');
  const [captured, setCaptured] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(false);

  useEffect(
    () => () => {
      micStreamRef.current?.getTracks().forEach(t => t.stop());
      camStreamRef.current?.getTracks().forEach(t => t.stop());
      vizRef.current?.dispose();
    },
    [],
  );

  const refreshDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setMicDevices(all.filter(d => d.kind === 'audioinput' && d.deviceId));
      setCamDevices(all.filter(d => d.kind === 'videoinput' && d.deviceId));
    } catch {
      /* the pickers just keep their current entries */
    }
  }, []);

  // Keep the pickers in sync when hardware is plugged in / unplugged.
  useEffect(() => {
    const md = navigator.mediaDevices;
    if (!md?.addEventListener) return;
    const onChange = () => void refreshDevices();
    md.addEventListener('devicechange', onChange);
    return () => md.removeEventListener('devicechange', onChange);
  }, [refreshDevices]);

  /** First grant uses the remembered device loosely (`ideal`); an explicit
   * pick from the select uses `exact` so the switch actually happens. */
  const enableMic = useCallback(
    async (deviceId?: string) => {
      const wasGranted = micState === 'granted';
      if (!wasGranted) setMicState('requesting');
      try {
        const preferred = deviceId ?? getPreferredDevice('audioinput');
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: deviceId
            ? { deviceId: { exact: deviceId } }
            : preferred
              ? { deviceId: { ideal: preferred } }
              : true,
        });
        micStreamRef.current?.getTracks().forEach(t => t.stop());
        micStreamRef.current = stream;
        const track = stream.getAudioTracks()[0];
        vizRef.current ??= createVizEngine();
        const analyser = vizRef.current.attach(track);
        setMicAnalyser(prev => {
          prev?.dispose();
          return analyser;
        });
        const settled = track.getSettings().deviceId ?? deviceId ?? '';
        setMicId(settled);
        setPreferredDevice('audioinput', settled || null);
        setMicState('granted');
        await refreshDevices();
      } catch {
        // A failed device *switch* keeps the previous working stream.
        setMicState(wasGranted ? 'granted' : 'denied');
      }
    },
    [micState, refreshDevices],
  );

  const enableCam = useCallback(
    async (deviceId?: string) => {
      const wasGranted = camState === 'granted';
      if (!wasGranted) setCamState('requesting');
      try {
        const preferred = deviceId ?? getPreferredDevice('videoinput');
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 1280 },
            ...(deviceId
              ? { deviceId: { exact: deviceId } }
              : preferred
                ? { deviceId: { ideal: preferred } }
                : {}),
          },
          audio: false,
        });
        camStreamRef.current?.getTracks().forEach(t => t.stop());
        camStreamRef.current = stream;
        setCamStream(stream);
        const track = stream.getVideoTracks()[0];
        const settled = track?.getSettings().deviceId ?? deviceId ?? '';
        setCamId(settled);
        setPreferredDevice('videoinput', settled || null);
        setCamState('granted');
        await refreshDevices();
      } catch {
        setCamState(wasGranted ? 'granted' : 'denied');
      }
    },
    [camState, refreshDevices],
  );

  // The preview <video> mounts only after access is granted, so bind the
  // stream from an effect rather than at getUserMedia time.
  useEffect(() => {
    if (videoRef.current && camStream) videoRef.current.srcObject = camStream;
  }, [camStream]);

  const capture = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0);
    canvas.toBlob(async blob => {
      if (!blob) return;
      setUploading(true);
      setUploadError(false);
      try {
        await candidateApi.postSelfie(applicationId, blob);
        setCaptured(true);
      } catch {
        // A verification photo is required server-side (preflight_join gates
        // the join on it), so surface the failure and let them retake it.
        setUploadError(true);
      } finally {
        setUploading(false);
      }
    }, 'image/webp');
  };

  const micBadge = permBadge(micState);
  const camBadge = permBadge(camState);
  // The verification selfie is always required, whatever the proctoring
  // setting — it identifies the candidate on the review page.
  const canContinue = micState === 'granted' && captured;
  const blocker =
    micState !== 'granted'
      ? 'Enable your microphone to continue.'
      : !canContinue
        ? 'Take your verification photo to continue.'
        : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          Camera & microphone
        </h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Grant access and pick which devices to use.
          {proctoringEnabled
            ? ' The interview is voice-first; the camera takes a verification photo now and periodic snapshots during the interview.'
            : ' The interview is voice-first; the camera is used once for your verification photo.'}
        </p>
      </div>

      {/* Microphone */}
      <section className="border" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <header className="flex items-center justify-between px-4 py-3 border-b">
          <span className="flex items-center gap-2 label-mono" style={{ color: 'var(--text-secondary)' }}>
            <Mic size={14} />
            Microphone
          </span>
          <Badge color={micBadge.color}>{micBadge.label}</Badge>
        </header>
        <div className="p-4 space-y-4">
          {micState === 'granted' ? (
            <>
              <Select
                label="Input device"
                value={micId}
                onChange={e => void enableMic(e.target.value)}
                options={micDevices.map((d, i) => ({
                  value: d.deviceId,
                  label: d.label || `Microphone ${i + 1}`,
                }))}
              />
              <div>
                <EqualizerBars analyser={micAnalyser} height={36} />
                <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                  Say something — the bars should move.
                </p>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {micState === 'denied'
                  ? 'Microphone access is blocked. Allow it in your browser settings (the camera/mic icon near the address bar), then try again.'
                  : 'Kandidly interviews you by voice, so it needs your microphone.'}
              </p>
              <Button
                variant={micState === 'denied' ? 'outline' : 'primary'}
                size="lg"
                className="w-full"
                loading={micState === 'requesting'}
                onClick={() => void enableMic()}
              >
                {micState === 'denied' ? 'Try again' : 'Enable microphone'}
              </Button>
            </>
          )}
        </div>
      </section>

      {/* Camera — always shown: the verification selfie is required whatever
          the proctoring setting */}
      <section className="border" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <header className="flex items-center justify-between px-4 py-3 border-b">
          <span className="flex items-center gap-2 label-mono" style={{ color: 'var(--text-secondary)' }}>
            <Video size={14} />
            Camera
          </span>
          <Badge color={camBadge.color}>{camBadge.label}</Badge>
        </header>
        <div className="p-4 space-y-4">
          {camState === 'granted' ? (
            <>
              <div className="relative overflow-hidden aspect-video bg-black border">
                <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
                {captured && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                    <div className="text-center space-y-2">
                      <CheckCircle2 size={32} className="mx-auto" style={{ color: 'var(--emerald-chip-text)' }} />
                      <p className="text-sm text-white font-medium">Photo captured</p>
                    </div>
                  </div>
                )}
              </div>
              <Select
                label="Camera"
                value={camId}
                onChange={e => {
                  void enableCam(e.target.value);
                }}
                options={camDevices.map((d, i) => ({
                  value: d.deviceId,
                  label: d.label || `Camera ${i + 1}`,
                }))}
              />
              {uploadError && (
                <p className="text-xs" style={{ color: 'var(--amber-chip-text)' }}>
                  Couldn't upload your photo. Please try taking it again.
                </p>
              )}
              <Button
                variant={captured ? 'outline' : 'primary'}
                size="lg"
                className="w-full"
                loading={uploading}
                onClick={capture}
              >
                {captured ? 'Retake photo' : 'Take verification photo'}
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {camState === 'denied'
                  ? 'Camera access is blocked. Allow it in your browser settings (the camera/mic icon near the address bar), then try again.'
                  : proctoringEnabled
                    ? 'A verification photo is required for this interview, and the camera stays on for periodic snapshots.'
                    : 'A verification photo is required for this interview. The camera is used only for this photo.'}
              </p>
              <Button
                variant={camState === 'denied' ? 'outline' : 'primary'}
                size="lg"
                className="w-full"
                loading={camState === 'requesting'}
                onClick={() => void enableCam()}
              >
                {camState === 'denied' ? 'Try again' : 'Enable camera'}
              </Button>
            </>
          )}
        </div>
      </section>

      <canvas ref={canvasRef} className="hidden" />

      {blocker && (
        <p className="text-xs text-center" style={{ color: 'var(--text-muted)' }}>
          {blocker}
        </p>
      )}
      <Button variant="primary" size="lg" className="w-full" disabled={!canContinue} onClick={onDone}>
        Continue
        <ArrowRight size={16} />
      </Button>
    </div>
  );
}

// ─── Step 3: Ready ────────────────────────────────────────────────────────────

function ReadyStep({
  applicationId,
  durationMinutes,
  onJoinSuccess,
}: {
  applicationId: string;
  durationMinutes: number;
  onJoinSuccess: (join: JoinOut) => void;
}) {
  const [polling, setPolling] = useState(false);
  const [lkUnavailable, setLkUnavailable] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setPolling(false);
  };

  const joinMutation = useMutation({
    mutationFn: () => candidateApi.join(applicationId),
    onSuccess: data => {
      stopPolling();
      onJoinSuccess(data);
    },
    onError: (err: unknown) => {
      const axiosErr = err as {
        response?: { status?: number; data?: { code?: string; retry_after_s?: number; message?: string } };
      };
      const status = axiosErr?.response?.status;
      const data = axiosErr?.response?.data;
      if (status === 202 && data?.retry_after_s != null) {
        // Plan/agent not ready yet — poll on a *single* interval. Every failed
        // poll re-enters onError, so guard against stacking new intervals.
        setJoinError(null);
        setPolling(true);
        if (!pollRef.current) {
          pollRef.current = setInterval(() => joinMutation.mutate(), data.retry_after_s! * 1000);
        }
      } else if (status === 500 || data?.code === 'internal_error') {
        stopPolling();
        setLkUnavailable(true);
      } else {
        // A blocking requirement (e.g. a missing consent/selfie returns 202
        // not_ready *without* retry_after_s) or an unexpected error — stop and
        // surface it rather than polling forever.
        stopPolling();
        setJoinError(
          data?.message ??
            "We couldn't start the interview. Please go back and make sure every step is complete.",
        );
      }
    },
  });

  // Clear any poll interval on unmount.
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  if (lkUnavailable) {
    return (
      <div className="space-y-6">
        <div
          className="rounded-xl border p-6 text-center space-y-3"
          style={{ borderColor: 'rgba(46,91,255,0.3)', background: 'rgba(46,91,255,0.05)' }}
        >
          <WifiOff size={24} className="mx-auto" style={{ color: 'var(--accent)' }} />
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            Voice interviews aren't enabled in this environment yet
          </p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            This is a development environment without LiveKit configured. The rest of the
            candidate flow works; voice interviews will be available once infrastructure is set up.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          You're all set
        </h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          A few things to know before you start.
        </p>
      </div>

      <div
        className="rounded-xl border p-5 space-y-3"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
      >
        {[
          { icon: '⏱', text: `The interview is up to ${durationMinutes} minutes long.` },
          { icon: '🎙', text: 'Speak clearly. The AI conducts the interview through your microphone.' },
          { icon: '🔄', text: 'Follow-up questions are normal — answer as thoroughly as you can.' },
          { icon: '🔁', text: 'You may rejoin once if disconnected.' },
        ].map((item, i) => (
          <div key={i} className="flex items-start gap-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
            <span className="text-base">{item.icon}</span>
            <span>{item.text}</span>
          </div>
        ))}
      </div>

      {joinError && (
        <p className="text-xs text-center text-amber-400">{joinError}</p>
      )}

      {polling ? (
        <div className="flex flex-col items-center gap-4 py-4">
          <AgentOrb analyser={null} size={96} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            Kandidly is getting ready…
          </p>
        </div>
      ) : (
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          loading={joinMutation.isPending}
          onClick={() => joinMutation.mutate()}
        >
          {joinError ? 'Try again' : 'Join Interview'}
          <ArrowRight size={16} />
        </Button>
      )}
    </div>
  );
}

// ─── Main lobby page ──────────────────────────────────────────────────────────

export default function CandidateLobby() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  const { data: app, isLoading } = useQuery<ApplicationOut>({
    queryKey: ['application', applicationId],
    queryFn: () => candidateApi.getApplication(applicationId!),
    enabled: !!applicationId,
  });

  // The verification selfie is always required (mirrors preflight_join);
  // proctoring only changes the consent copy and the monitoring checkbox.
  const proctoringEnabled = app?.proctoring_enabled !== false;
  const steps = ['Consent', 'Devices', 'Ready'];
  const readyStep = steps.length - 1;

  // If already in_lobby or beyond, skip straight to ready
  const appState = app?.state;
  useEffect(() => {
    if (!appState) return;
    if (appState === 'in_lobby' || appState === 'in_interview') {
      setStep(readyStep);
    }
  }, [appState, readyStep]);

  if (isLoading) {
    return (
      <LobbyLayout>
        <div className="flex justify-center py-16"><Spinner size={24} /></div>
      </LobbyLayout>
    );
  }

  return (
    <LobbyLayout>
      <div className="mb-8">
        <Stepper steps={steps} current={step} />
      </div>

      {step === 0 && (
        <ConsentStep
          applicationId={applicationId!}
          proctoringEnabled={proctoringEnabled}
          onDone={() => setStep(1)}
        />
      )}
      {step === 1 && (
        <DevicesStep
          applicationId={applicationId!}
          proctoringEnabled={proctoringEnabled}
          onDone={() => setStep(2)}
        />
      )}
      {step === readyStep && (
        <ReadyStep
          applicationId={applicationId!}
          durationMinutes={app?.duration_minutes ?? 30}
          onJoinSuccess={join => {
            // Hand the LiveKit credentials to the interview room via router
            // state so it can connect without a second /join round-trip.
            navigate(`/apply/${applicationId}/interview`, { state: join });
          }}
        />
      )}
    </LobbyLayout>
  );
}

function LobbyLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen py-12 px-4"
      style={{ background: 'var(--background)' }}
    >
      <div className="max-w-lg mx-auto">
        <div className="flex justify-center mb-8">
          <div
            className="size-7 flex items-center justify-center font-display font-bold text-sm"
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
