"""UUIDv7 generation in the application layer (SPEC D16). Index locality without
DB-side generation. Falls back to a spec-compliant local implementation if the
`uuid7` package is unavailable."""

from __future__ import annotations

import os
import time
from uuid import UUID

try:  # prefer the maintained package
    from uuid_extensions import uuid7 as _uuid7  # type: ignore

    def uuid7() -> UUID:
        return _uuid7()

except Exception:  # pragma: no cover - fallback path

    def uuid7() -> UUID:
        """RFC 9562 UUIDv7: 48-bit ms timestamp, version/variant bits, random tail."""
        unix_ms = int(time.time() * 1000)
        rand = os.urandom(10)
        b = bytearray(16)
        b[0] = (unix_ms >> 40) & 0xFF
        b[1] = (unix_ms >> 32) & 0xFF
        b[2] = (unix_ms >> 24) & 0xFF
        b[3] = (unix_ms >> 16) & 0xFF
        b[4] = (unix_ms >> 8) & 0xFF
        b[5] = unix_ms & 0xFF
        b[6] = 0x70 | (rand[0] & 0x0F)  # version 7
        b[7] = rand[1]
        b[8] = 0x80 | (rand[2] & 0x3F)  # variant 10
        b[9:16] = rand[3:10]
        return UUID(bytes=bytes(b))


def new_id() -> UUID:
    """Canonical PK generator used across all tables."""
    return uuid7()
