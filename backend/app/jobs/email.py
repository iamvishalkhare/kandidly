"""send_email job. Retryable transport failures (429/5xx/network) back off
exponentially via arq Retry; everything else — rendering errors, rejected
payloads, exhausted tries — is logged loudly and swallowed so a bad email can
never become a worker crash loop. API code enqueues via enqueue_email."""

from __future__ import annotations

import structlog
from arq import Retry

from app.core import email as email_core
from app.core.queue import enqueue

log = structlog.get_logger(__name__)

MAX_TRIES = 5
_BACKOFF_BASE_S = 30  # 30s, 60s, 120s, 240s between the 5 tries


async def send_email(ctx: dict, to: str, template: str, context: dict) -> None:
    job_try = ctx.get("job_try", 1)
    try:
        message_id = await email_core.send(to=to, template=template, context=context)
    except email_core.EmailSendError as exc:
        if exc.retryable and job_try < MAX_TRIES:
            defer = _BACKOFF_BASE_S * 2 ** (job_try - 1)
            log.warning(
                "email_send_retry", to=to, template=template, try_=job_try, defer_s=defer,
                error=str(exc),
            )
            raise Retry(defer=defer) from exc
        log.error(
            "email_send_failed", to=to, template=template, tries=job_try, error=str(exc)
        )
        return
    except Exception as exc:  # noqa: BLE001 — bad template/context: retries can't fix it
        log.error("email_render_failed", to=to, template=template, error=str(exc))
        return
    log.info("email_sent", to=to, template=template, message_id=message_id)


async def enqueue_email(to: str, template: str, context: dict) -> None:
    """Fire-and-forget enqueue for API code."""
    await enqueue("send_email", to, template, context)
