"""CAPTCHA verification — Google reCAPTCHA v3 (SPEC §12.5, bot/DDoS defense).

Server-side siteverify guard for expensive public candidate actions. Exposed as
a FastAPI dependency factory mirroring `rate_limit`:

    @router.post("/form/submit", dependencies=[require_captcha("form_submit")])

The client runs `grecaptcha.execute(siteKey, {action})` and sends the resulting
token in the `X-Recaptcha-Token` header. reCAPTCHA v3 is score-based (0.0–1.0)
and returns the `action` it was issued for; we enforce both.

Fails OPEN when no secret key is configured (dev parity with the rate limiter),
so local flows work without Google keys — set KANDIDLY_RECAPTCHA_SECRET_KEY in
prod to enforce. A siteverify network/transport error also fails open
(availability over strictness in v1, matching ratelimit.py); an explicit
`success: false` from Google fails closed.
"""

from __future__ import annotations

import httpx
from fastapi import Depends, Request

from app.core.config import settings
from app.core.errors import AppError

_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def verify_recaptcha(token: str, *, remoteip: str | None, action: str) -> None:
    """Verify a reCAPTCHA v3 token or raise ``captcha_failed`` (403).

    No-ops when no secret is configured. `action` is the expected v3 action name
    the token was minted for.
    """
    secret = settings.recaptcha_secret_key
    if not secret:
        return  # unconfigured → fail open (dev)
    if not token:
        raise AppError("captcha_failed", "Captcha verification required")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _VERIFY_URL,
                data={"secret": secret, "response": token, "remoteip": remoteip or ""},
            )
        data = resp.json()
    except Exception:  # noqa: BLE001 — Google unreachable → fail open (availability)
        return

    if not data.get("success"):
        raise AppError(
            "captcha_failed",
            "Captcha verification failed",
            detail={"errors": data.get("error-codes")},
        )
    # v3 only: the token is bound to the action it was issued for.
    got_action = data.get("action")
    if action and got_action and got_action != action:
        raise AppError("captcha_failed", "Captcha action mismatch")
    score = data.get("score")
    if score is not None and score < settings.recaptcha_min_score:
        raise AppError(
            "captcha_failed", "Captcha score too low", detail={"score": score}
        )


def require_captcha(action: str):
    """Dependency enforcing a valid reCAPTCHA v3 token for `action`. Reads the
    `X-Recaptcha-Token` header and the client IP (behind a proxy: first hop of
    `X-Forwarded-For`)."""

    async def _dep(request: Request) -> None:
        token = request.headers.get("x-recaptcha-token", "")
        fwd = request.headers.get("x-forwarded-for")
        ip = (
            fwd.split(",")[0].strip()
            if fwd
            else (request.client.host if request.client else None)
        )
        await verify_recaptcha(token, remoteip=ip, action=action)

    return Depends(_dep)
