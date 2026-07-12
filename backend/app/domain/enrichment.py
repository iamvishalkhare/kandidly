"""Source scraping for interview-context enrichment (SPEC §8.6).

Given a candidate's form answers, find the GitHub / personal-site / blog URLs
they submitted, fetch and distil each into a compact digest an interviewer can
use to ask sharp, specific follow-ups.

Design rules:
- **Best effort, never raises.** A failed scrape must never block plan generation
  or the interview — each source is captured with a per-source status.
- **Graceful LLM degradation.** When a backend LLM key is configured we summarise
  each source into a `SourceDigest`; otherwise we keep cleaned text (`text_only`),
  mirroring how the plan pipeline falls back today.
- **SSRF guarded.** Only http/https, and public IPs only (private/loopback/
  link-local/reserved hosts are rejected before any request is made).

URLs are identified from `field_hints` roles (the confirmed mechanism) with a
plain URL-detection fallback so an untagged form still yields sources.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

# field_hints role → source kind. See app/db/seed.py FIELD_HINTS.
ROLE_KIND = {"github_url": "github", "portfolio_url": "website", "blog_url": "blog"}
URL_ROLES = frozenset(ROLE_KIND)

_MAX_SOURCES = 5
_HTTP_TIMEOUT = 10.0
_MAX_HTML_BYTES = 3_000_000
_TEXT_ONLY_CHARS = 6000  # kept when we can't summarise
_EXCERPT_CHARS = 1200  # kept alongside a digest
_SUMMARISE_INPUT_CHARS = 40_000
_UA = "KandidlyBot/1.0 (+interview context enrichment)"

_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Source selection
# --------------------------------------------------------------------------- #
def _first_url(value: object) -> str | None:
    """Extract a normalised http(s) URL from a form answer value, if any."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    m = _URL_RE.search(s)
    if m:
        return m.group(0).rstrip(".,;")
    # Bare host like "github.com/alice" or "www.site.dev" → assume https.
    if re.match(r"^(www\.|[\w-]+\.)+[a-z]{2,}(/|$)", s, re.IGNORECASE):
        return "https://" + s
    return None


def select_sources(answers: dict, field_hints: dict) -> list[dict]:
    """Return an ordered, de-duplicated `[{kind, url}]` list to scrape.

    1. Fields whose `field_hints[key].role` is a URL role (precise).
    2. Fallback: any answer value that looks like a URL (kind inferred).
    """
    out: list[dict] = []
    seen: set[str] = set()

    for key, hint in (field_hints or {}).items():
        role = (hint or {}).get("role")
        if role in URL_ROLES:
            url = _first_url((answers or {}).get(key))
            if url and url not in seen:
                seen.add(url)
                out.append({"kind": ROLE_KIND[role], "url": url})

    for value in (answers or {}).values():
        url = _first_url(value)
        if url and url not in seen:
            seen.add(url)
            kind = "github" if "github.com" in url.lower() else "website"
            out.append({"kind": kind, "url": url})

    return out[:_MAX_SOURCES]


# --------------------------------------------------------------------------- #
# SSRF guard
# --------------------------------------------------------------------------- #
async def _is_public_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, p.hostname, None)
    except Exception:  # noqa: BLE001 — DNS failure → treat as unsafe/unreachable
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False
    return True


# --------------------------------------------------------------------------- #
# Fetchers → cleaned text content
# --------------------------------------------------------------------------- #
def _github_username(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    first = path.split("/")[0]
    # Skip non-user paths (orgs pages, gists, etc. still resolve as a login).
    return first or None


async def _fetch_github(client: httpx.AsyncClient, url: str) -> tuple[dict, str]:
    """Return (structured github dict, rendered text) via the GitHub REST API."""
    user = _github_username(url)
    if not user:
        raise ValueError("no github username in url")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": _UA}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    prof_resp = await client.get(f"https://api.github.com/users/{user}", headers=headers)
    prof = prof_resp.raise_for_status().json()
    repos_resp = await client.get(
        f"https://api.github.com/users/{user}/repos",
        params={"sort": "pushed", "per_page": 10, "type": "owner"},
        headers=headers,
    )
    repos_raw = repos_resp.json() if repos_resp.status_code == 200 else []
    repos = [
        {
            "name": r.get("name"),
            "description": r.get("description"),
            "language": r.get("language"),
            "stars": r.get("stargazers_count"),
            "topics": r.get("topics") or [],
        }
        for r in (repos_raw or [])
        if not r.get("fork")
    ][:8]

    structured = {
        "login": prof.get("login"),
        "name": prof.get("name"),
        "bio": prof.get("bio"),
        "company": prof.get("company"),
        "blog": prof.get("blog"),
        "followers": prof.get("followers"),
        "public_repos": prof.get("public_repos"),
        "html_url": prof.get("html_url"),
        "top_repos": repos,
    }

    lines = [f"GitHub profile: {structured['name'] or ''} (@{structured['login']})"]
    if structured["bio"]:
        lines.append(f"Bio: {structured['bio']}")
    if structured["company"]:
        lines.append(f"Company: {structured['company']}")
    lines.append(f"{structured['public_repos']} public repos, {structured['followers']} followers")
    if repos:
        lines.append("Recent repositories:")
        for r in repos:
            topics = f" [topics: {', '.join(r['topics'])}]" if r["topics"] else ""
            lines.append(
                f"- {r['name']} ({r['language'] or 'n/a'}, ★{r['stars']}): "
                f"{r['description'] or 'no description'}{topics}"
            )
    return structured, "\n".join(lines)


async def _fetch_html(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Return (title, cleaned visible text) for a website/blog URL."""
    from bs4 import BeautifulSoup

    resp = await client.get(url, headers={"User-Agent": _UA}, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text[: _MAX_HTML_BYTES * 2]
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "form"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    text = " ".join(soup.get_text(separator=" ").split())
    return title, text


# --------------------------------------------------------------------------- #
# Summarisation (degrades to text_only)
# --------------------------------------------------------------------------- #
async def _summarise(kind: str, url: str, content: str) -> dict | None:
    """LLM digest of scraped content, or None when no LLM key / call fails."""
    from app.llm.clients import source_summarizer
    from app.llm.prompts import load_prompt

    try:
        agent = source_summarizer()
        prompt = (
            load_prompt("enrich", "v1")
            .replace("{source_kind}", kind)
            .replace("{source_url}", url)
            .replace("{source_content}", content[:_SUMMARISE_INPUT_CHARS])
        )
        result = await agent.run(prompt)
        digest = getattr(result, "output", None) or getattr(result, "data", None)
        return digest.model_dump() if digest else None
    except Exception as exc:  # noqa: BLE001 — no key / provider error → text_only
        log.info("source_summarise_skipped", url=url, error=str(exc))
        return None


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
async def scrape_sources(sources: list[dict]) -> list[dict]:
    """Scrape + distil each `{kind, url}`; returns per-source result records.

    Never raises — a failing source is recorded with status='failed'.
    """
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for src in sources:
            kind, url = src.get("kind", "website"), src.get("url", "")
            rec: dict = {"kind": kind, "url": url, "fetched_at": datetime.now(UTC).isoformat()}
            try:
                if kind == "github":
                    structured, content = await _fetch_github(client, url)
                    rec["github"] = structured
                else:
                    if not await _is_public_url(url):
                        raise ValueError("url is not a reachable public address")
                    title, content = await _fetch_html(client, url)
                    rec["title"] = title

                if not content.strip():
                    raise ValueError("no content extracted")

                digest = await _summarise(kind, url, content)
                if digest is not None:
                    rec["mode"] = "digest"
                    rec["digest"] = digest
                    rec["text"] = content[:_EXCERPT_CHARS]
                else:
                    rec["mode"] = "text_only"
                    rec["text"] = content[:_TEXT_ONLY_CHARS]
                rec["status"] = "done"
            except Exception as exc:  # noqa: BLE001 — best effort, never blocks
                log.warning("source_scrape_failed", kind=kind, url=url, error=str(exc))
                rec["status"] = "failed"
                rec["error"] = str(exc)[:200]
            results.append(rec)
    return results
