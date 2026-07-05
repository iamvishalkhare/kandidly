"""Data-channel codec tests (SPEC §9.5, §18.1)."""

from __future__ import annotations

import json

import pytest

from datamsg import (
    MAX_BYTES,
    PROTOCOL_VERSION,
    EnvelopeTooLarge,
    caption_final,
    control_timer,
    decode,
    encode,
)


def test_roundtrip():
    raw = caption_final("kandidly", "Hello", 3)
    env = decode(raw)
    assert env["v"] == PROTOCOL_VERSION
    assert env["type"] == "caption.final"
    assert env["payload"] == {"speaker": "kandidly", "text": "Hello", "turn_seq": 3}


def test_timer_message():
    env = decode(control_timer(120, 1680, "normal"))
    assert env["payload"]["remaining_s"] == 1680


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        encode("bogus.type", {})


def test_oversize_rejected():
    with pytest.raises(EnvelopeTooLarge):
        encode("caption.final", {"speaker": "k", "text": "x" * (MAX_BYTES + 10), "turn_seq": 1})


def test_decode_rejects_bad_version():
    raw = json.dumps({"v": 99, "type": "caption.final", "ts": "x", "payload": {}})
    with pytest.raises(ValueError):
        decode(raw)


def test_decode_requires_object_payload():
    raw = json.dumps({"v": 1, "type": "caption.final", "ts": "x", "payload": []})
    with pytest.raises(ValueError):
        decode(raw)
