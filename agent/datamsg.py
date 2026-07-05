"""Data-channel envelope codec (SPEC §9.5). Topic `kandidly`; JSON envelope
capped at 15 KB: {"v":1,"type","ts","payload"}. Pure — used by the agent to
build outbound messages and to parse inbound client batches."""

from __future__ import annotations

import json
from datetime import datetime, timezone

PROTOCOL_VERSION = 1
TOPIC = "kandidly"
MAX_BYTES = 15 * 1024

# Message types (SPEC §9.5).
CAPTION_PARTIAL = "caption.partial"
CAPTION_FINAL = "caption.final"
CONTROL_TIMER = "control.timer"
CONTROL_STATE = "control.state"
PROCTOR_EVENT = "proctor.event"
OBSERVER_INJECT_ACK = "observer.inject.ack"

_ALL_TYPES = frozenset(
    {
        CAPTION_PARTIAL,
        CAPTION_FINAL,
        CONTROL_TIMER,
        CONTROL_STATE,
        PROCTOR_EVENT,
        OBSERVER_INJECT_ACK,
    }
)


class EnvelopeTooLarge(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(msg_type: str, payload: dict, *, ts: str | None = None) -> bytes:
    """Build a wire envelope. Raises on unknown type or oversize (SPEC §9.5)."""
    if msg_type not in _ALL_TYPES:
        raise ValueError(f"unknown data-channel type: {msg_type!r}")
    envelope = {
        "v": PROTOCOL_VERSION,
        "type": msg_type,
        "ts": ts or _now_iso(),
        "payload": payload,
    }
    raw = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise EnvelopeTooLarge(f"envelope {len(raw)}B exceeds {MAX_BYTES}B cap")
    return raw


def decode(raw: bytes | str) -> dict:
    """Parse + validate an inbound envelope. Returns the envelope dict."""
    envelope = json.loads(raw)
    if envelope.get("v") != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {envelope.get('v')}")
    if envelope.get("type") not in _ALL_TYPES:
        raise ValueError(f"unknown data-channel type: {envelope.get('type')!r}")
    if not isinstance(envelope.get("payload"), dict):
        raise ValueError("payload must be an object")
    return envelope


# Typed constructors ---------------------------------------------------------
def caption_partial(speaker: str, text: str) -> bytes:
    return encode(CAPTION_PARTIAL, {"speaker": speaker, "text": text})


def caption_final(speaker: str, text: str, turn_seq: int) -> bytes:
    return encode(CAPTION_FINAL, {"speaker": speaker, "text": text, "turn_seq": turn_seq})


def control_timer(elapsed_s: int, remaining_s: int, phase: str) -> bytes:
    return encode(CONTROL_TIMER, {"elapsed_s": elapsed_s, "remaining_s": remaining_s, "phase": phase})


def control_state(status: str) -> bytes:
    return encode(CONTROL_STATE, {"status": status})


def observer_inject_ack(injection_id: str, status: str) -> bytes:
    return encode(OBSERVER_INJECT_ACK, {"injection_id": injection_id, "status": status})
