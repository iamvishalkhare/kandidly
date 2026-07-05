# Kandidly

AI voice interviewer for candidate screening. Requisition → KYI form → live voice
interview with Kandidly → rubric-scored, evidence-backed report.

See `docs/SPEC.md` for the normative build specification (v1.1). Naming (tables,
columns, states, env vars, JSON fields) is normative — see SPEC §0.5.

## Architecture

| Service  | Path       | Role |
|----------|------------|------|
| backend  | `backend/` | FastAPI REST APIs, state machines, token issuance, system of record |
| agent    | `agent/`   | LiveKit Agents worker — the realtime interview brain (STT→LLM→TTS) |
| worker   | `backend/` (arq) | Background jobs: resume parse, plan gen, scoring, reports, sweepers |
| web      | `web/`     | React + Vite SPA: admin console + candidate flow |

Data plane: PostgreSQL 16 (system of record), Redis 7 (arq + live state),
S3-compatible object store (MinIO in dev), LiveKit Cloud (rooms).

## Quick start (dev)

Container runtime is **Podman (rootless)** — see SPEC §3.5.

```bash
cp infra/.env.example infra/.env      # fill in provider keys
cd infra && make up                   # podman compose up
make logs                             # tail logs
make down
```

Backend runs on :8000, web on :5173, MinIO console on :9001.

### Backend without containers

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed
uv run uvicorn app.main:app --reload --port 8000
```

## Build status

Foundation (SPEC §19 T01–T10) is scaffolded. See `docs/STATUS.md` for what is
implemented vs. remaining across Phases 1–5.

## Tests

```bash
cd backend && uv run pytest
```
