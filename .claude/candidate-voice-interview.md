# Candidate `/i/:token` flow + live AI voice interview — session notes

_Session ending 2026-07-09. Author: Claude (Opus 4.8). This documents work that is **uncommitted** on `main`._

## What this session did

1. **Completed the candidate-facing `/i/:token` flow** (it existed as a skeleton) and **built the live AI voice interview room**.
2. **Made the real AI voice interview work end-to-end** through **LiveKit Cloud + LiveKit inference** (STT/TTS/LLM via one credential set — no separate Deepgram/Cartesia/Anthropic accounts).
3. Fixed a series of dev/UX bugs found while driving it.

Everything below was **verified server-side** (agent joins room → interview `live` → LLM greeting → turns written to DB → captions/timer on data channel → `/join` mints a real token). The only thing not verifiable headless is the browser mic/audio itself.

## Architecture (where things live)

- **Frontend candidate flow:** `web/src/pages/candidate/{Landing,Form,Lobby,Interview,Done}.tsx`.
  - Route order: `/i/:token` (Landing) → `/apply/:id/form` → `/apply/:id/lobby` → `/apply/:id/interview` (NEW) → `/apply/:id/done`. Routes in `web/src/App.tsx`; **Interview is lazy-loaded** (keeps the ~480 KB `livekit-client` chunk off every other page).
  - **Interview room** `Interview.tsx`: connects with `livekit-client` `Room`, publishes mic, subscribes to the agent's audio track, reads the `kandidly` data channel for captions/timer/state. Data-channel decoder: `web/src/lib/interviewChannel.ts` (mirrors `agent/datamsg.py` — keep in sync).
  - Field vocab: the candidate form renders JSON-Schema `x-field` types; the console builder uses `type`. Backend translates (`app/domain/builder.py`).
- **Agent** (`agent/worker.py`) — REWRITTEN into a real interviewer on **livekit-agents 1.6.4**:
  - `WorkerOptions(entrypoint_fnc=...)` with **no `agent_name`** → **automatic dispatch** to any room a participant creates (candidate rooms are `kndl-{interview_id}`).
  - Uses `inference.STT/LLM/TTS` (LiveKit Cloud). Bootstraps from backend `GET /internal/interviews/{id}/bootstrap`, builds interviewer instructions from the plan's seed questions, sets status `live`/`ended`, writes turns via `POST /internal/.../turns` (monotonic seq via a single-consumer queue), and publishes `caption.final` / `control.timer` / `control.state` on the `kandidly` data channel.
  - Reuses `agent/backend_client.py`, `agent/datamsg.py`, `agent/config.py`.
- **Backend token minting:** `app/domain/interviews.py::mint_candidate_token` — needs the `livekit-api` package (added this session).
- **Interview lifecycle contract:** `app/api/internal.py` (bootstrap/turns/status), guarded by `X-Service-Token`.

## Config / env (LiveKit)

- User's LiveKit Cloud creds live in `backend/scripts/.env.local` as `LIVEKIT_URL/API_KEY/API_SECRET` (standard names; also used by `backend/scripts/livekit_test.py`).
- Mapped into `infra/.env` as `KANDIDLY_LIVEKIT_URL/API_KEY/API_SECRET` (**gitignored**). Compose auto-loads `infra/.env`.
- `infra/compose.yml`: added `KANDIDLY_LIVEKIT_*` to the **backend** service env (was missing — backend needs them to mint tokens). Agent service already had them.
- **Agent inference models** (override via env `KANDIDLY_INFERENCE_STT/_LLM/_TTS/_TTS_VOICE`), defaults in `agent/worker.py`:
  - STT `assemblyai/universal-streaming`, LLM `google/gemini-2.5-flash`, TTS `cartesia/sonic-2`.
  - **Valid model ids are a fixed enum** in the installed package: introspect `livekit.agents.inference` (`STTModels/LLMModels/TTSModels`). `google/gemini-2.0-flash` is **NOT** valid (caused `404 'Error getting model definition'` — first bug). Google valid ids: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3-flash`, etc.

## How to run & test

```bash
cd infra && podman compose -f compose.yml up --build -d postgres redis minio minio-init backend worker agent
cd web && npm run dev            # native Vite on :5173 (backend :8000). The web CONTAINER is not used.
```
- Containers: `kandidly_{postgres,redis,minio,backend,worker,agent}_1`. Backend has `--reload` (mounts source); **worker (arq) does NOT auto-reload — restart it after changing backend job code**. Agent mounts source but **restart the agent to pick up module-level changes** (e.g. model ids).
- **Dev auth:** `GET /api/public/dev-users` → candidates with bearer tokens. Landing shows a picker.
- **Demo requisition** created this session: **REQ-0001**, invite token **`ernIAddKupQjdnMgREQHaG`** → `http://localhost:5173/i/ernIAddKupQjdnMgREQHaG`. (Every seeded candidate already has a terminal app on the seed requisition `ENG-001` / link `KirqeiGar8FDVgYdpXRbP8`, so that link always routes to Done.)
- **Dev reset (NEW):** `POST /api/public/dev-reset {token,email}` abandons a candidate's live app so the next claim is fresh (dev-only, 404s outside `AUTH_DEV_MODE`). The Landing page now **always shows the picker and resets-on-pick**, so the dev loop is: open link → pick anyone → fresh interview, every time (no localStorage/cookie clearing). Hard refresh only needed to load new *code*.

## Gotchas discovered (important)

1. **Backend commits AFTER the response is sent.** `get_session()` yields then commits; FastAPI 0.106+ runs `yield`-dependency teardown post-response. So rapid **write-then-read** across requests races (e.g. PATCH form → immediate submit; claim → immediate GET → 404). The real app is mostly protected because the form autosaves incrementally as the user types. **Verification scripts must poll** until the write is readable. (Not fixed — pre-existing architecture.)
2. **`generate_plan` waited the full 90s** when no resume was uploaded (`resume_parse_status` stays `None`, never terminal). **Fixed** in `app/jobs/planning.py::_wait_for_resume` to return early when `resume_file_id is None`. (Restart the worker to apply.)
3. **Agent audio race (silent agent):** attaching the remote track to a React-rendered `<audio ref>` fails because the ref is often `null` when the track arrives. **Fixed** in `Interview.tsx`: use `track.attach()` → append the element to `<body>`; if autoplay is blocked, show "Tap to enable interview audio" (`room.startAudio()`).
4. `mint_candidate_token` needs `livekit-api` in the **backend** image (was `No module named 'livekit'` → 500). Added to `backend/pyproject.toml` + `uv.lock`; rebuild the backend image.
5. Landing was reusing a stale localStorage token (recruiter token → `/claim` 403 "Candidate role required"). Reworked (see below).

## Files changed this session (all uncommitted)

- **New:** `web/src/pages/candidate/Interview.tsx`, `web/src/lib/interviewChannel.ts`.
- **Frontend edits:** `web/src/App.tsx` (route + lazy Suspense), `web/src/pages/candidate/{Landing,Form,Lobby,Done}.tsx`, `web/src/lib/api.ts` (candidate/interview + `publicApi.devReset`), `web/package.json` (+`livekit-client`).
- **Agent:** `agent/worker.py` (full rewrite; was a `SystemExit` skeleton).
- **Backend:** `backend/pyproject.toml` + `uv.lock` (+`livekit-api`), `app/api/public.py` (`/dev-reset`), `app/jobs/planning.py` (resume-wait fix).
- **Infra:** `infra/compose.yml` (LiveKit env for backend), `infra/.env` (creds, gitignored).
- Earlier frontend polish also folded in: Landing error-map fix (`maxed`), Form autosave flush, Lobby polling/selfie/a11y fixes.

## Status: works vs. still needs a key

- ✅ **Real voice interview + transcript storage works** via LiveKit inference (interview LLM/STT/TTS are billed through LiveKit, independent of any backend key).
- ⚠️ **No BACKEND LLM key** (`KANDIDLY_ANTHROPIC_API_KEY` / OpenAI / Google all empty). Consequences: resume parsing, **tailored** question plans, and **post-interview scoring/report are disabled** — the plan falls back to `fallback_generic` and no `Report` is produced. Add a backend LLM key to `infra/.env` + `make down && make up` to enable those.

## Suggested next steps

- Add a backend LLM key → tailored plans + resume parse + scored reports; then verify the finalize→scoring→report pipeline end-to-end.
- Remove the temporary `await asyncio.sleep(3)` in `app/api/console.py` deploy/update endpoints (leftover from splash-screen testing).
- Commit this work (it's all uncommitted on `main`).
- Consider proper candidate auth (currently dev-picker only; WorkOS is the planned path).

---

# Follow-up session (2026-07-09, later) — reCAPTCHA + interview context enrichment

_Two features added after the notes above. **#1 reCAPTCHA is COMMITTED (`037a2e5` on `main`); #2 enrichment is UNCOMMITTED.** The original candidate-flow + voice-interview work above was also committed as part of `037a2e5`._

## 1. reCAPTCHA v3 on the screening-form submit — COMMITTED (`037a2e5`)

Anti-bot/DDoS gate on `POST /api/candidate/applications/{id}/form/submit` (the costly step: creates the `Interview` + enqueues `generate_plan`).

- **Backend:** `app/core/captcha.py` — `require_captcha("form_submit")` dependency (mirrors `app/core/ratelimit.py`). Reads the `X-Recaptcha-Token` header, POSTs Google `siteverify`, enforces `success` + `action` + `score >= KANDIDLY_RECAPTCHA_MIN_SCORE` (default 0.5). New error code `captcha_failed` → 403 (`app/core/errors.py`). Wired into `submit_form` via `dependencies=[...]`.
- **Degrades open:** when `KANDIDLY_RECAPTCHA_SECRET_KEY` is empty, verification is **skipped** (dev parity with the fail-open rate limiter); a siteverify network error also fails open; an explicit `success:false` fails closed.
- **Frontend:** site key served via `/api/public/config` (`ConfigOut.recaptcha_site_key`); `web/src/lib/recaptcha.ts` (invisible v3 loader/executor); `Form.tsx` mints a token on submit → `candidateApi.submitForm(id, token)` sets the header; shows a friendly message on `captcha_failed`.
- **Env:** `KANDIDLY_RECAPTCHA_SITE_KEY` / `_SECRET_KEY` / `_MIN_SCORE` in `infra/.env` (+ `.env.example`, `compose.yml` `x-backend-env`). **The user set REAL keys in `infra/.env`, so enforcement is currently ON** — headless/API submits without a valid v3 token now 403. Get keys from the reCAPTCHA admin console; `localhost` must be an allowed domain.

## 2. Interview context enrichment — UNCOMMITTED

**Goal:** at form submit, assemble a rich context bundle (form answers + parsed resume + **scraped GitHub/site/blog** + requisition details) and cache it in Redis so the agent asks sharper, candidate-specific questions/follow-ups at room-load.

**Pipeline (`submit → room load`):**
```
submit_form ─► cache PARTIAL bundle in Redis now (form + requisition, sync)
          ├─► enqueue enrich_sources   (scrape → summarize → persist enrichment)
          └─► enqueue generate_plan    (waits resume+enrichment, folds sources
                                        into the plan LLM, caches FULL bundle "ready")
room load ─► agent bootstrap ─► reads Redis (rebuilds from Postgres on a miss)
                              ─► _build_instructions adds "Candidate background"
```

**Where things live:**
- **Scraper** `app/domain/enrichment.py`: `select_sources(answers, field_hints)` picks URLs by `field_hints` role (`github_url`/`portfolio_url`/`blog_url`) with a URL auto-detect fallback; `scrape_sources()` — GitHub via REST API, sites via `httpx` + **BeautifulSoup** (lazy `from bs4 import ...`), **SSRF-guarded** (public IPs only), LLM-summarize (`source_summarizer()` + `enrich_v1.md` + `SourceDigest`) else `text_only`. **Best-effort, never raises.**
- **Cache/assembly** `app/core/cache.py` (Redis JSON) + `app/domain/interview_context.py` (`assemble_context` / `cache_context` / `get_cached_context` / `rebuild_context`). Redis key `interview:context:{interview_id}`, TTL 24h.
- **Job** `app/jobs/enrichment.py::enrich_sources` (registered in `app/jobs/worker.py`).
- **Plan** `app/jobs/planning.py`: `_wait_for_resume` → **`_wait_for_inputs`** (awaits resume AND enrichment terminal); `_sources_digest()` feeds `{sources_json}` into `plan_v1.md`; caches the full bundle after `write_plan`.
- **Bootstrap** `app/api/internal.py`: reads Redis (rebuilds from PG on miss), fills the previously-`None` `candidate_display_name`/`resume_summary`/`form_digest` and adds a `context` object.
- **Agent** `agent/worker.py`: `_background_section(ctx)` → "Candidate background" block in `_build_instructions`.

**Data model:** `form_submissions.enrichment` (JSONB) + `enrichment_status` — **migration `0006_add_submission_enrichment.py`** (already applied to the dev DB). Shape: `{"sources":[{kind,url,status,mode,digest|text,github?,fetched_at}]}`.

**URL role tagging:** roles live in `FormTemplate.field_hints` (`{key:{use_in_plan,role}}`). Seeded `github` field tagged `role: github_url` in `app/db/seed.py FIELD_HINTS`. Fallback auto-detect handles untagged templates.

**Deps/infra:** added `beautifulsoup4` to `backend/pyproject.toml`; **root `uv.lock` regenerated** (`uv lock`) and **backend + worker images rebuilt** (bs4 baked in). Optional `KANDIDLY_GITHUB_TOKEN` (lifts GitHub rate limit) in `config.py` + compose + `.env.example`.

**Verified e2e** (against the running stack, no LLM key): GitHub scrape `done` (torvalds, 8 repos) + website via bs4; summarize correctly degraded to `text_only`; full pipeline `enrich_sources`→`generate_plan`→cached `ready` bundle; HTTP `bootstrap` returns populated `context`; **cold-cache miss rebuilds from Postgres** and re-caches; SSRF/loopback + DNS-fail + malformed URLs all fail gracefully.

**Still needs a backend LLM key** (same caveat as above): without `KANDIDLY_ANTHROPIC_API_KEY`, source digests are `text_only` and plans are `fallback_generic` — the bundle still caches and the agent still gets form + requisition + raw scraped text. Add the key for source-grounded seed questions + `SourceDigest` summaries.

**To run after pulling this:** `make -C infra migrate` (applies 0006), rebuild backend+worker for bs4 (`podman compose build backend worker`), restart the worker (arq doesn't auto-reload) and agent.
