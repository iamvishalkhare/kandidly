/**
 * Interview audio recorder — mixes the local mic and the agent's remote audio
 * through a Web Audio graph and records the blend with MediaRecorder,
 * uploading ~15 s chunks to the backend as they are produced (see
 * POST /api/candidate/interviews/{id}/recording/chunks and docs/ARTIFACTS.md).
 *
 * Imperative controller rather than a hook: Interview.tsx drives LiveKit via
 * refs inside effects, and recording must never re-render the call UI or
 * break it — every failure path here is retried, then swallowed.
 *
 * Chunking only works for containers whose sliced blobs byte-concatenate into
 * one valid stream (webm/opus — header lives in chunk 0). Safari records
 * audio/mp4, whose slices are NOT concatenable, so on non-webm browsers we
 * buffer locally and upload a single blob as chunk 0 on stop.
 */

import { candidateApi } from './api';

const CHUNK_MS = 15_000;
const UPLOAD_RETRIES = 3;
const RETRY_BASE_MS = 1_000;
const WEBM_MIME = 'audio/webm;codecs=opus';

export interface InterviewRecorder {
  /** Mix another audio track into the recording (mic, agent audio, …). */
  addTrack(track: MediaStreamTrack): void;
  /** Flush pending uploads and signal /recording/complete. Idempotent. */
  stop(): Promise<void>;
}

const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

export function createInterviewRecorder(interviewId: string): InterviewRecorder | null {
  if (typeof MediaRecorder === 'undefined' || typeof AudioContext === 'undefined') return null;

  const streamingMime = MediaRecorder.isTypeSupported(WEBM_MIME) ? WEBM_MIME : null;
  const ctx = new AudioContext();
  const destination = ctx.createMediaStreamDestination();
  const sources: MediaStreamAudioSourceNode[] = [];

  let recorder: MediaRecorder | null = null;
  let startedAt: string | null = null;
  let nextSeq = 0;
  let uploadedChunks = 0;
  let mime = streamingMime ?? '';
  const bufferedParts: Blob[] = []; // non-webm fallback: upload once on stop

  // Sequential upload queue — chunks land in order, retries with backoff,
  // failures stay queued for one last attempt during the final flush.
  const pending: Array<{ seq: number; blob: Blob }> = [];
  let uploading: Promise<void> = Promise.resolve();

  const uploadWithRetry = async (seq: number, blob: Blob): Promise<boolean> => {
    for (let attempt = 0; attempt < UPLOAD_RETRIES; attempt++) {
      try {
        await candidateApi.uploadRecordingChunk(interviewId, seq, blob);
        uploadedChunks += 1;
        return true;
      } catch {
        await sleep(RETRY_BASE_MS * 3 ** attempt);
      }
    }
    return false;
  };

  const drainQueue = () => {
    uploading = uploading.then(async () => {
      while (pending.length > 0) {
        const item = pending[0];
        const ok = await uploadWithRetry(item.seq, item.blob);
        if (!ok) return; // leave the rest queued; the final flush retries
        pending.shift();
      }
    });
  };

  const ensureStarted = () => {
    if (recorder) return;
    recorder = new MediaRecorder(
      destination.stream,
      streamingMime
        ? { mimeType: streamingMime, audioBitsPerSecond: 32_000 }
        : { audioBitsPerSecond: 32_000 },
    );
    mime = recorder.mimeType || mime || 'audio/webm';
    startedAt = new Date().toISOString();
    recorder.ondataavailable = event => {
      if (!event.data || event.data.size === 0) return;
      if (streamingMime) {
        pending.push({ seq: nextSeq++, blob: event.data });
        drainQueue();
      } else {
        bufferedParts.push(event.data);
      }
    };
    if (streamingMime) recorder.start(CHUNK_MS);
    else recorder.start();
  };

  let stopPromise: Promise<void> | null = null;

  const doStop = async () => {
    const active = recorder;
    recorder = null;
    if (!active || !startedAt) {
      void ctx.close().catch(() => {});
      return;
    }
    try {
      // Wait for the recorder's final ondataavailable before flushing.
      if (active.state !== 'inactive') {
        await new Promise<void>(resolve => {
          active.onstop = () => resolve();
          try {
            active.stop();
          } catch {
            resolve();
          }
        });
      }
      if (!streamingMime && bufferedParts.length > 0) {
        pending.push({ seq: nextSeq++, blob: new Blob(bufferedParts, { type: mime }) });
      }
      drainQueue();
      // Bounded flush: give trailing uploads a fair chance, then move on.
      await Promise.race([uploading, sleep(10_000)]);
      await candidateApi.completeRecording(interviewId, {
        chunks: uploadedChunks,
        started_at: startedAt,
        mime,
      });
    } catch {
      // Best-effort: finalize_interview enqueues process_recording as a
      // safety net, so a lost complete call still yields a recording.
    } finally {
      sources.forEach(s => s.disconnect());
      void ctx.close().catch(() => {});
    }
  };

  return {
    addTrack(track: MediaStreamTrack) {
      if (track.kind !== 'audio' || stopPromise) return;
      try {
        const source = ctx.createMediaStreamSource(new MediaStream([track]));
        source.connect(destination);
        sources.push(source);
        void ctx.resume().catch(() => {});
        ensureStarted();
      } catch {
        // Mixing failure must never break the call.
      }
    },
    stop() {
      stopPromise ??= doStop();
      return stopPromise;
    },
  };
}
