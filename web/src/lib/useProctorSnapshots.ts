/**
 * Periodic webcam snapshots during the live interview, uploaded to the
 * existing proctoring ingest (POST /api/candidate/interviews/{id}/snapshots).
 * One frame every intervalS seconds (from /api/public/config); every frame
 * is analyzed server-side, so the cadence directly sets the analysis volume.
 *
 * Degrades gracefully: camera denial posts a single `camera_off` proctor
 * event (flags the session for manual review) and notifies the caller for a
 * banner — the interview itself is never blocked. Upload failures are silent;
 * the loop gives up after 10 consecutive failures.
 */

import { candidateApi } from './api';

const CAPTURE_WIDTH = 480;
const MAX_CONSECUTIVE_FAILURES = 10;

export interface SnapshotLoop {
  stop(): void;
}

export function startSnapshotLoop(
  interviewId: string,
  opts: { intervalS: number; onCameraDenied?: () => void },
): SnapshotLoop {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stream: MediaStream | null = null;
  let consecutiveFailures = 0;

  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;

  const stop = () => {
    stopped = true;
    if (timer !== null) clearTimeout(timer);
    stream?.getTracks().forEach(t => t.stop());
    stream = null;
    video.srcObject = null;
  };

  const schedule = () => {
    if (stopped) return;
    timer = setTimeout(() => void capture(), Math.max(1, opts.intervalS) * 1000);
  };

  const capture = async () => {
    if (stopped) return;
    try {
      const vw = video.videoWidth || 640;
      const vh = video.videoHeight || 480;
      const canvas = document.createElement('canvas');
      canvas.width = CAPTURE_WIDTH;
      canvas.height = Math.max(1, Math.round((vh / vw) * CAPTURE_WIDTH));
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('no 2d context');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>(resolve =>
        canvas.toBlob(resolve, 'image/webp', 0.7),
      );
      if (!blob) throw new Error('toBlob failed');
      await candidateApi.uploadSnapshot(interviewId, blob, new Date().toISOString());
      consecutiveFailures = 0;
    } catch {
      consecutiveFailures += 1;
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        stop();
        return;
      }
    }
    schedule();
  };

  void (async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 } },
        audio: false,
      });
      if (stopped) {
        stream.getTracks().forEach(t => t.stop());
        return;
      }
      video.srcObject = stream;
      await video.play();
      schedule();
    } catch {
      opts.onCameraDenied?.();
      try {
        await candidateApi.postProctorEvents(interviewId, [
          {
            type: 'camera_off',
            client_ts: new Date().toISOString(),
            payload: { stage: 'interview_start' },
          },
        ]);
      } catch {
        /* best-effort */
      }
    }
  })();

  return { stop };
}
