/**
 * Interview data-channel decoder.
 *
 * Mirrors `agent/datamsg.py` (this repo keeps FE/BE contracts hand-mirrored):
 * topic `kandidly`, JSON envelope `{ v, type, ts, payload }` capped at 15 KB.
 * The agent publishes captions, a countdown timer, and interview state over
 * this channel; the room UI (`web/src/pages/candidate/Interview.tsx`)
 * subscribes and renders them. Keep the message types and payload shapes in
 * sync with that Python file.
 */

export const PROTOCOL_VERSION = 1;
export const CHANNEL_TOPIC = 'kandidly';

export type Speaker = 'candidate' | 'kandidly';

export type InterviewMessage =
  | { type: 'caption.partial'; ts: string; speaker: string; text: string }
  | { type: 'caption.final'; ts: string; speaker: string; text: string; turn_seq: number }
  | { type: 'control.timer'; ts: string; elapsed_s: number; remaining_s: number; phase: string }
  | { type: 'control.state'; ts: string; status: string }
  | { type: 'proctor.event'; ts: string; payload: Record<string, unknown> }
  | { type: 'observer.inject.ack'; ts: string; injection_id: string; status: string };

const KNOWN_TYPES = new Set<InterviewMessage['type']>([
  'caption.partial',
  'caption.final',
  'control.timer',
  'control.state',
  'proctor.event',
  'observer.inject.ack',
]);

const decoder = new TextDecoder();

/**
 * Parse an inbound envelope. Returns `null` (rather than throwing) for anything
 * unrecognized — malformed JSON, wrong protocol version, or unknown type — so
 * the room UI can safely ignore frames it doesn't understand.
 */
export function decodeInterviewMessage(raw: Uint8Array | string): InterviewMessage | null {
  let env: { v?: number; type?: string; ts?: string; payload?: Record<string, unknown> };
  try {
    const text = typeof raw === 'string' ? raw : decoder.decode(raw);
    env = JSON.parse(text);
  } catch {
    return null;
  }

  if (env?.v !== PROTOCOL_VERSION) return null;
  const type = env.type as InterviewMessage['type'] | undefined;
  if (!type || !KNOWN_TYPES.has(type)) return null;

  const p = (env.payload ?? {}) as Record<string, unknown>;
  const ts = typeof env.ts === 'string' ? env.ts : '';

  switch (type) {
    case 'caption.partial':
      return { type, ts, speaker: String(p.speaker ?? ''), text: String(p.text ?? '') };
    case 'caption.final':
      return {
        type,
        ts,
        speaker: String(p.speaker ?? ''),
        text: String(p.text ?? ''),
        turn_seq: Number(p.turn_seq ?? 0),
      };
    case 'control.timer':
      return {
        type,
        ts,
        elapsed_s: Number(p.elapsed_s ?? 0),
        remaining_s: Number(p.remaining_s ?? 0),
        phase: String(p.phase ?? ''),
      };
    case 'control.state':
      return { type, ts, status: String(p.status ?? '') };
    case 'observer.inject.ack':
      return {
        type,
        ts,
        injection_id: String(p.injection_id ?? ''),
        status: String(p.status ?? ''),
      };
    case 'proctor.event':
      return { type, ts, payload: p };
    default:
      return null;
  }
}

/** Format a remaining-seconds count as `m:ss` (clamped at zero). */
export function formatRemaining(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${String(rem).padStart(2, '0')}`;
}
