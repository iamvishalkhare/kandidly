/**
 * Audio-reactive voice visuals for the interview UI.
 *
 * AgentOrb — Kandidly's presence: concentric cobalt rings that scale and glow
 * with the agent's live TTS level (a slow synthetic breath when idle).
 * EqualizerBars — a mirrored FFT bar strip for the candidate's mic; also
 * doubles as the lobby mic-check meter.
 *
 * Both poll a VoiceAnalyser (lib/audioViz.ts) inside requestAnimationFrame
 * and write straight to the DOM/canvas, so they stay out of React's render
 * path entirely.
 */

import { useEffect, useRef } from 'react';
import type { VoiceAnalyser } from '../lib/audioViz';
import { cn } from '../lib/utils';

const REDUCED_MOTION =
  typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export function AgentOrb({
  analyser,
  size,
  className,
}: {
  analyser: VoiceAnalyser | null;
  size?: number;
  className?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const audio = analyser?.readLevel() ?? 0;
      // Idle breath keeps the instrument visibly alive between turns; real
      // audio takes over the moment the agent produces sound.
      const breath = REDUCED_MOTION ? 0 : 0.05 + 0.05 * Math.sin((now - start) / 900);
      const lvl = audio > 0.04 ? audio : Math.max(audio, breath);
      el.style.setProperty('--lvl', lvl.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [analyser]);

  return (
    <div
      ref={rootRef}
      className={cn('voice-orb', className)}
      style={size ? { width: size, height: size } : undefined}
      aria-hidden="true"
    >
      <div className="orb-glow" />
      <div className="orb-ring orb-ring-3" />
      <div className="orb-ring orb-ring-2" />
      <div className="orb-ring orb-ring-1" />
      <div className="orb-core font-display">K</div>
    </div>
  );
}

export function EqualizerBars({
  analyser,
  height = 44,
  className,
}: {
  analyser: VoiceAnalyser | null;
  height?: number;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const styles = getComputedStyle(canvas);
    const accent = styles.getPropertyValue('--accent').trim() || '#2e5bff';
    const baseline = styles.getPropertyValue('--outline-variant').trim() || '#434656';

    const dpr = () => Math.min(2, window.devicePixelRatio || 1);
    const resize = () => {
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr()));
      canvas.height = Math.max(1, Math.round(height * dpr()));
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const BAR_W = 3;
    const GAP = 4;
    let bands = new Float32Array(0);
    let raf = 0;

    const draw = () => {
      const scale = dpr();
      const W = canvas.width;
      const H = canvas.height;
      const step = (BAR_W + GAP) * scale;
      const count = Math.max(9, Math.floor(W / step));
      const half = Math.ceil(count / 2);
      if (bands.length !== half) bands = new Float32Array(half);
      if (analyser) analyser.readBands(bands);
      else bands.fill(0);

      ctx.clearRect(0, 0, W, H);
      const x0 = (W - (count * step - GAP * scale)) / 2;
      const center = (count - 1) / 2;
      for (let i = 0; i < count; i++) {
        // Mirrored around the middle: low voice bands bloom from the center.
        const v = bands[Math.min(half - 1, Math.round(Math.abs(i - center)))] ?? 0;
        const shaped = Math.pow(v, 0.75);
        const h = Math.max(2 * scale, shaped * (H - 2 * scale));
        const active = shaped > 0.04;
        ctx.fillStyle = active ? accent : baseline;
        ctx.globalAlpha = active ? 0.45 + shaped * 0.55 : 0.7;
        ctx.fillRect(x0 + i * step, (H - h) / 2, BAR_W * scale, h);
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [analyser, height]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: '100%', height, display: 'block' }}
      aria-hidden="true"
    />
  );
}
