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
