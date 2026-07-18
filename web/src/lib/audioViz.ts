/**
 * Web Audio analysis for the live-interview voice visuals.
 *
 * One engine = one AudioContext. attach() taps a MediaStreamTrack with an
 * AnalyserNode and returns a reader that render loops poll each frame —
 * nothing here touches React state. Analysis is passive (no output
 * connection), so it never affects what the candidate hears, and disposing
 * the engine tears down the graph without stopping the tracks themselves.
 */

export interface VoiceAnalyser {
  /** Smoothed 0..1 loudness (fast attack, time-corrected release). */
  readLevel(): number;
  /** Fill `out` with 0..1 spectrum magnitudes across the voice band. */
  readBands(out: Float32Array): void;
  dispose(): void;
}

export interface VizEngine {
  attach(track: MediaStreamTrack): VoiceAnalyser | null;
  /** Best-effort resume after a user gesture (autoplay policies). */
  resume(): void;
  dispose(): void;
}

const FFT_SIZE = 1024;
/** Ignore spectrum above this — speech energy lives below ~4 kHz. */
const VOICE_MAX_HZ = 4200;

export function createVizEngine(): VizEngine {
  if (typeof AudioContext === 'undefined') {
    return { attach: () => null, resume: () => {}, dispose: () => {} };
  }
  const ctx = new AudioContext();
  const disposers = new Set<() => void>();

  return {
    attach(track: MediaStreamTrack): VoiceAnalyser | null {
      if (track.kind !== 'audio') return null;
      try {
        const source = ctx.createMediaStreamSource(new MediaStream([track]));
        const analyser = ctx.createAnalyser();
        analyser.fftSize = FFT_SIZE;
        analyser.smoothingTimeConstant = 0.72;
        source.connect(analyser);
        void ctx.resume().catch(() => {});

        const timeBuf = new Uint8Array(analyser.fftSize);
        const freqBuf = new Uint8Array(analyser.frequencyBinCount);
        const maxBin = Math.min(
          analyser.frequencyBinCount - 1,
          Math.round((VOICE_MAX_HZ / (ctx.sampleRate / 2)) * analyser.frequencyBinCount),
        );
        let level = 0;
        let lastTs = 0;

        const dispose = () => {
          disposers.delete(dispose);
          try {
            source.disconnect();
          } catch {
            /* graph already torn down */
          }
        };
        disposers.add(dispose);

        return {
          readLevel() {
            analyser.getByteTimeDomainData(timeBuf);
            let sum = 0;
            for (let i = 0; i < timeBuf.length; i++) {
              const d = (timeBuf[i] - 128) / 128;
              sum += d * d;
            }
            const rms = Math.sqrt(sum / timeBuf.length);
            const target = Math.min(1, rms * 5.5);
            // Release is time-corrected so callers at any polling rate (60 fps
            // canvas loops, ~6 Hz status ticks) see the same decay curve.
            const now = performance.now();
            const dt = lastTs ? Math.min(200, now - lastTs) : 16.7;
            lastTs = now;
            level = target > level ? target : level * Math.pow(0.92, dt / 16.7);
            return level;
          },
          readBands(out: Float32Array) {
            if (out.length === 0) return;
            analyser.getByteFrequencyData(freqBuf);
            const span = Math.max(1, maxBin / out.length);
            for (let b = 0; b < out.length; b++) {
              const start = Math.floor(b * span);
              const end = Math.max(start + 1, Math.floor((b + 1) * span));
              let acc = 0;
              for (let i = start; i < end; i++) acc += freqBuf[i];
              out[b] = acc / ((end - start) * 255);
            }
          },
          dispose,
        };
      } catch {
        return null;
      }
    },
    resume() {
      void ctx.resume().catch(() => {});
    },
    dispose() {
      disposers.forEach(d => d());
      void ctx.close().catch(() => {});
    },
  };
}
