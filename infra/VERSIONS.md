# Pinned versions

Exact versions are locked at build time (`uv lock`, `npm install`) and satisfy
the majors below. The `uv.lock` at repo root is committed and used by
`uv sync --frozen` in CI/containers. `[VERIFY-DOC]` names MUST be confirmed
against official docs before relying on API surface (SPEC §0.2, §3).

## Runtime / tooling (recorded from build host)

| Tool            | Version used | Notes |
|-----------------|--------------|-------|
| Podman          | 5.8.2        | rootless (SPEC D17, §3.5) |
| compose provider| —            | `podman compose` delegates; record provider + version here |
| Python          | 3.12         | container base (host may differ) |
| Node            | 26.x         | web build |
| uv              | 0.11+        | Python package manager (SPEC D18) |
| PostgreSQL      | 16           | managed in prod |
| Redis           | 7            | arq + live state |

## Backend (majors — see `backend/pyproject.toml`; exact pins in `uv.lock`)

| Package                     | Major | Notes |
|-----------------------------|-------|-------|
| fastapi                     | 0.11x | |
| uvicorn                     | 0.3x  | |
| sqlalchemy                  | 2.x   | async + asyncpg |
| alembic                     | 1.x   | |
| asyncpg                     | 0.30  | |
| pydantic                    | 2.x   | |
| pydantic-settings           | 2.x   | |
| pydantic-ai                 | 0.x   | `[VERIFY-DOC]` structured output / TestModel API |
| arq                         | 0.26  | `[VERIFY-DOC]` |
| httpx                       | 0.28  | |
| aioboto3 / boto3            | —     | S3 |
| jsonschema                  | 4.x   | form submission validation |
| structlog                   | 24.x  | |
| prometheus-client           | 0.2x  | |
| PyMuPDF / python-docx       | —     | resume text extraction `[VERIFY-DOC]` |
| pytesseract                 | —     | OCR fallback `[VERIFY-DOC]` |
| insightface / onnxruntime   | —     | identity check (buffalo_l) `[VERIFY-DOC]` |
| pyjwt / cryptography        | —     | auth contract |

## Agent (see `agent/pyproject.toml`)

| Package                       | Notes |
|-------------------------------|-------|
| livekit-agents                | `[VERIFY-DOC]` job dispatch / AgentSession |
| livekit-plugins-deepgram      | STT nova-3 `[VERIFY-DOC]` |
| livekit-plugins-cartesia      | TTS sonic `[VERIFY-DOC]` |
| livekit-plugins-anthropic     | interviewer LLM `[VERIFY-DOC]` |
| livekit-plugins-silero        | VAD `[VERIFY-DOC]` |

## Web (see `web/package.json`)

| Package                       | Notes |
|-------------------------------|-------|
| react / react-dom             | 18 |
| vite                          | 5 |
| typescript                    | 5 |
| @livekit/components-react     | `[VERIFY-DOC]` |
| @tanstack/react-query         | 5 |
| react-hook-form               | 7 |
| @mediapipe/tasks-vision       | face detector `[VERIFY-DOC]` |
| tailwindcss                   | 3 |
