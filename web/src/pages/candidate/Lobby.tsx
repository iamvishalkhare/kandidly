/**
 * /apply/:applicationId/lobby — 3-step pre-interview flow.
 * Step 1: Consent (scroll text + 2 checkboxes)
 * Step 2: Camera check (getUserMedia preview, capture selfie)
 * Step 3: Ready (what to expect + Join button)
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, AlertTriangle, Mic, Video, WifiOff } from 'lucide-react';
import { candidateApi } from '../../lib/api';
import { Button, Stepper, Spinner } from '../../components/ui';
import { cn } from '../../lib/utils';
import type { ApplicationOut, JoinOut } from '../../lib/types';

const CONSENT_VERSION = 'v1-2026-07';

// ─── Step 1: Consent ─────────────────────────────────────────────────────────

function ConsentStep({ applicationId, onDone }: { applicationId: string; onDone: () => void }) {
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

  const canProceed = recordingAck && monitoringAck;

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
        <p><strong style={{ color: 'var(--text-primary)' }}>Monitoring Disclosure</strong></p>
        <p>
          During the interview, our system may take periodic screenshots to verify your identity
          and ensure interview integrity. This data is stored securely and used only for
          evaluation and compliance purposes.
        </p>
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
        <CheckItem
          checked={monitoringAck}
          onChange={setMonitoringAck}
          label="I understand that periodic screenshots may be taken for identity verification."
        />
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

// ─── Step 2: Camera check ─────────────────────────────────────────────────────

function CameraStep({ applicationId, onDone }: { applicationId: string; onDone: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [permError, setPermError] = useState(false);
  const [captured, setCaptured] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let s: MediaStream | null = null;
    let active = true;
    setPermError(false);
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: false })
      .then(ms => {
        if (!active) {
          ms.getTracks().forEach(t => t.stop());
          return;
        }
        s = ms;
        setStream(ms);
        if (videoRef.current) {
          videoRef.current.srcObject = ms;
        }
      })
      .catch(() => {
        if (active) setPermError(true);
      });

    return () => {
      active = false;
      s?.getTracks().forEach(t => t.stop());
    };
  }, [retryKey]);

  const capture = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
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
        // A verification photo is required server-side (preflight_join gates the
        // join on it), so we can't silently proceed — surface the failure and
        // let the candidate retake it.
        setUploadError(true);
      } finally {
        setUploading(false);
      }
    }, 'image/webp');
  };

  if (permError) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Camera check</h2>
        </div>
        <div
          className="rounded-xl border p-6 text-center space-y-3"
          style={{ borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.05)' }}
        >
          <AlertTriangle size={24} className="mx-auto text-amber-400" />
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            Camera access needed
          </p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            A verification photo is required for this interview. Please allow camera access
            in your browser settings, then try again.
          </p>
        </div>
        <Button variant="outline" size="lg" className="w-full" onClick={() => setRetryKey(k => k + 1)}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Camera check</h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Make sure your camera is working and take a quick selfie.
        </p>
      </div>

      {/* Video preview */}
      <div className="relative rounded-xl overflow-hidden aspect-video bg-black border" style={{ borderColor: 'var(--border)' }}>
        <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
        <canvas ref={canvasRef} className="hidden" />
        {captured && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <div className="text-center space-y-2">
              <CheckCircle2 size={32} className="text-emerald-400 mx-auto" />
              <p className="text-sm text-white font-medium">Selfie captured</p>
            </div>
          </div>
        )}
      </div>

      {/* Device indicators */}
      <div className="flex gap-3">
        <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
          <Video size={14} className={stream ? 'text-emerald-400' : 'text-zinc-500'} />
          Camera {stream ? 'active' : 'inactive'}
        </div>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
          <Mic size={14} className="text-zinc-500" />
          Mic (checked at interview start)
        </div>
      </div>

      {uploadError && (
        <p className="text-xs text-center text-amber-400">
          Couldn't upload your photo. Please try taking it again.
        </p>
      )}

      {captured ? (
        <Button variant="primary" size="lg" className="w-full" onClick={onDone}>
          Continue
          <ArrowRight size={16} />
        </Button>
      ) : (
        <Button
          variant="outline"
          size="lg"
          className="w-full"
          loading={uploading}
          disabled={!stream}
          onClick={capture}
        >
          {uploadError ? 'Retake selfie' : 'Take selfie'}
        </Button>
      )}
    </div>
  );
}

// ─── Step 3: Ready ────────────────────────────────────────────────────────────

function ReadyStep({
  applicationId,
  onJoinSuccess,
}: {
  applicationId: string;
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
          style={{ borderColor: 'rgba(139,124,246,0.2)', background: 'rgba(139,124,246,0.05)' }}
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
          { icon: '⏱', text: 'The interview is up to 30 minutes long.' },
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
        <div className="flex flex-col items-center gap-3 py-4">
          <Spinner size={24} />
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

const STEPS = ['Consent', 'Camera', 'Ready'];

export default function CandidateLobby() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);

  const { data: app, isLoading } = useQuery<ApplicationOut>({
    queryKey: ['application', applicationId],
    queryFn: () => candidateApi.getApplication(applicationId!),
    enabled: !!applicationId,
  });

  // If already in_lobby or beyond, skip consent
  const appState = app?.state;
  useEffect(() => {
    if (!appState) return;
    if (appState === 'in_lobby' || appState === 'in_interview') {
      setStep(2); // skip to ready
    }
  }, [appState]);

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
        <Stepper steps={STEPS} current={step} />
      </div>

      {step === 0 && (
        <ConsentStep
          applicationId={applicationId!}
          onDone={() => setStep(1)}
        />
      )}
      {step === 1 && (
        <CameraStep
          applicationId={applicationId!}
          onDone={() => setStep(2)}
        />
      )}
      {step === 2 && (
        <ReadyStep
          applicationId={applicationId!}
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
            className="size-7 rounded-md flex items-center justify-center text-white font-bold text-sm"
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
