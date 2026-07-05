"""Invite link generation + resolution (SPEC §8.5)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models import InviteLink, Requisition

_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
TOKEN_LEN = 22  # ~131 bits


def generate_token() -> str:
    """22-char base62 token; never sequential (SPEC §8.5)."""
    return "".join(secrets.choice(_BASE62) for _ in range(TOKEN_LEN))


@dataclass(frozen=True)
class LinkResolution:
    status_ok: bool
    reason: str | None
    requisition: Requisition | None
    link: InviteLink | None


def resolve(link: InviteLink | None, requisition: Requisition | None) -> LinkResolution:
    """Pure evaluation of a link's usability. `reason` ∈
    {revoked, expired, maxed, requisition_closed, not_open_yet}."""
    now = datetime.now(UTC)

    def bad(reason: str) -> LinkResolution:
        return LinkResolution(False, reason, requisition, link)

    if link is None or requisition is None:
        return bad("expired")  # unknown token → treat as expired/invalid landing
    if link.revoked_at is not None:
        return bad("revoked")
    if link.expires_at is not None and link.expires_at <= now:
        return bad("expired")
    if link.max_uses is not None and link.use_count >= link.max_uses:
        return bad("maxed")
    if requisition.status == "closed":
        return bad("requisition_closed")
    if requisition.status in ("draft", "paused"):
        return bad("not_open_yet")
    if requisition.opens_at is not None and requisition.opens_at > now:
        return bad("not_open_yet")
    if requisition.closes_at is not None and requisition.closes_at <= now:
        return bad("requisition_closed")
    return LinkResolution(True, None, requisition, link)
