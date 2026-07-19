"""Transactional email: jinja2 rendering + a thin transport abstraction.

Two transports, selected by settings.email_transport ("resend" | "console"),
defaulting to resend only when an API key is configured so dev/tests never
send real mail. The console transport logs the rendered email and appends it
to the module-level OUTBOX so tests (and a curious dev) can inspect it.

Sending is expected to run inside the send_email arq job (app/jobs/email.py),
which maps EmailSendError.retryable onto arq retries with backoff. API code
should enqueue via app.jobs.email.enqueue_email, not call send() inline.

Templates live in app/emails/<name>/{subject.txt,body.html,body.txt} over a
shared base layout. Rendering uses StrictUndefined: a missing context var is
a loud TemplateError, not silently empty copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.config import settings

log = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "emails"
_RESEND_URL = "https://api.resend.com/emails"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def render_email(template: str, context: dict) -> RenderedEmail:
    """Render subject + both body parts for a template in app/emails/."""
    subject = _env.get_template(f"{template}/subject.txt").render(context)
    return RenderedEmail(
        subject=" ".join(subject.split()),  # headers are one line
        html=_env.get_template(f"{template}/body.html").render(context),
        text=_env.get_template(f"{template}/body.txt").render(context),
    )


class EmailSendError(Exception):
    """Transport failure. retryable=True (429/5xx/network) means the arq job
    wrapper should back off and retry; False (rejected payload, bad auth) means
    retrying can never succeed."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        self.retryable = retryable
        super().__init__(message)


class EmailTransport(Protocol):
    async def send(self, *, to: str, message: RenderedEmail) -> str | None:
        """Deliver; returns the provider message id (None when there is none)."""
        ...  # pragma: no cover


# Console-transport sink for tests/dev inspection (bounded; oldest dropped).
OUTBOX: list[dict] = []
_OUTBOX_MAX = 100


class ConsoleTransport:
    """Dev/test transport: log the rendered email instead of sending it."""

    async def send(self, *, to: str, message: RenderedEmail) -> str | None:
        OUTBOX.append({"to": to, "from": settings.email_from, **message.__dict__})
        del OUTBOX[:-_OUTBOX_MAX]
        log.info(
            "email_console",
            to=to,
            from_=settings.email_from,
            subject=message.subject,
            text=message.text,
        )
        return None


class ResendTransport:
    """POST https://api.resend.com/emails. A client can be injected for tests."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def send(self, *, to: str, message: RenderedEmail) -> str | None:
        payload = {
            "from": settings.email_from,
            "to": [to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
        try:
            if self._client is not None:
                resp = await self._client.post(_RESEND_URL, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(_RESEND_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EmailSendError(f"resend request failed: {exc}", retryable=True) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise EmailSendError(
                f"resend {resp.status_code}: {resp.text[:500]}", retryable=True
            )
        if resp.status_code >= 400:
            raise EmailSendError(
                f"resend {resp.status_code}: {resp.text[:500]}", retryable=False
            )
        return resp.json().get("id")


_transports: dict[str, EmailTransport] = {}


def get_transport() -> EmailTransport:
    mode = settings.email_transport or ("resend" if settings.resend_api_key else "console")
    if mode not in ("resend", "console"):
        raise EmailSendError(f"unknown email transport {mode!r}", retryable=False)
    if mode not in _transports:
        _transports[mode] = ResendTransport() if mode == "resend" else ConsoleTransport()
    return _transports[mode]


async def send(*, to: str, template: str, context: dict) -> str | None:
    """Render and deliver one email; returns the provider message id."""
    message = render_email(template, context)
    return await get_transport().send(to=to, message=message)
