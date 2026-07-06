# Kandidly — Build Status

Last updated: 2026-07-06 (schema evolution for console UI). Tracks progress against SPEC §19 + phase gates.

## Working right now (verified against the running Podman stack)
- **Backend**: 42 endpoints, all returning the SPEC §12 error envelope on failure. 211 unit tests green (`uv run pytest` in `backend/`; 27 more in `agent/`).
- **Candidate journey (live-tested)**: link resolve → claim → autosave → resume upload (S3/MinIO) → submit → plan generation (fallback bank without an LLM key) → `plan_ready` → consent/selfie/lobby. Join returns a friendly panel while LiveKit is unconfigured.
- **Admin journey**: requisitions list/detail/create/status, invite links create/revoke, applications list/detail, transcript, report view + review flow, funnel, template/rubric list + publish.
- **Text-chat interview harness (SPEC §18.5 Phase-1)**: `POST /api/admin/interviews/{id}/chat/start` + `/chat/reply` drive the interviewer LLM with the control-prefix protocol; turns/decisions/node states persist normally; ends → finalize → scoring enqueued. Returns a clear 503 until `KANDIDLY_ANTHROPIC_API_KEY` is set. UI: "Interview (Text)" tab on the admin application page.
- **Web UI**: full dark-minimal rebuild (React 19 + Vite + Tailwind). 11 routes: candidate landing/form/lobby/done + admin dashboard/requisitions/detail/application/forms/rubrics + 404. Dynamic KYI form renderer (all 8 x-field types), resume upload with parse polling, 3-step lobby, dev role-switcher via `/api/public/dev-users`. `npm run build` + `npm run lint` clean.
- **uv workspace**: root `pyproject.toml` with backend+agent members; dev deps in PEP-735 `[dependency-groups]` so `uv sync && uv run pytest` works.

## To unlock next (needs user input)
- `KANDIDLY_ANTHROPIC_API_KEY` in `infra/.env` + `make down && make up` → real plan generation, resume extraction, text interviews, scoring.
- `KANDIDLY_LIVEKIT_*` (+ Deepgram/Cartesia keys) → voice interviews (Phase 2 wiring still pending).

## Session log
- **2026-07-06 (schema for console UI)**: migration `0001` frozen into explicit DDL (verified pg_dump-identical; the `use_alter` FK cycle constraints must be added via `op.create_foreign_key` — metadata autogenerate silently drops them). New migration `0003_orgs_console`: `organizations` (+ default org, `workos_org_id`) and `catalog_entries` tables; `org_id` FKs on users/requisitions/templates/rubrics; users `display_name/avatar_url/workos_user_id/status` (WorkOS-ready, users now owned by our DB); requisitions `code` (REQ-#### from sequence) `/domain/technical_requirements[]/role_objective/sample_questions`; interviews `code` (INT-1001+ from sequence) + `audio_waveform` JSONB peaks; `invite_links.click_count` (incremented on `/i/{token}` resolve); `proctoring_snapshots.signal`; `reports.review_decision` CHECK (`shortlist|reject|hold`, Literal in API); **scores rescaled to 0–100** (`evaluations.final_score`, `reports.overall_score`; LLM runs stay 1–5 anchors, converted via `anchor_to_score100` at aggregation; `v_score_distribution` recreated with decile buckets). `InterviewConfig.tone` added. New storage key builders `recording_key`/`report_key`. Rich seed: 6 requisitions across domains + 6 finished interview pipelines on ENG-001 (turns, criterion scores, evaluations, reviewed reports, proctor snapshots w/ signals, generated WAV recordings + peaks in MinIO); idempotent per candidate. **Bug fixed**: `record_audit` passed a UUID into BIGSERIAL `audit_log.id` → every audited admin write rolled back after the 200 was sent (asyncpg int64 bind error); review decisions now persist. 247 backend tests green; ruff clean. Console `/console` pages still render frontend mocks by design — console APIs are the next step.
- **2026-07-05 (early)**: foundation T01–T11 built + verified (see git history once committed).
- **2026-07-05 (Gemini)**: uv workspace, partial web app, admin read endpoints, `reports.review_decision/notes` columns. Bugs fixed afterwards: `User.name` (×2), wrong `transition()` signature, missing `report.status='final'`.
- **2026-07-05 (evening)**: fixed all 500s (incl. flush-ordering bug on resume upload — models use raw FK columns, so inserts must be flushed before rows referencing them), catch-all error envelope, dev-users endpoint, proctoring domain + ingest routes (§10.2–10.3, consent-gated), text-chat harness + chat UI, full dark UI rebuild (Sonnet agent), provider-key env bridge with friendly 503.

## Remaining (priority order)
1. **Integration test (§18.2)**: full journey claim→form→submit→plan→text-interview (FunctionModel)→finalize→scoring (TestModel)→report against the real DB — no provider keys needed; guards the whole loop.
2. **Voice pipeline (Phase 2, T13–T15)**: livekit-agents wiring in `agent/worker.py` (`[VERIFY-DOC]`), room page UI (lobby currently shows friendly panel when LiveKit unset), egress, rejoin, Redis heartbeats. Blocked on user providing LiveKit/Deepgram/Cartesia keys to test.
3. **Proctoring frontend (Phase 4, T18)**: snapshot capture loop + browser-event batching in the room page (backend routes ready + rate-limited); identity_check job (§10.5).
4. **Observer view + injection UI (T20)** — backend inject/observer-token routes exist.
5. **Analytics (T21)**: cost ledger surfacing; report HTML render → S3 (`html_file_id` currently NULL).
6. **Hardening (T22)**: E1–E20 test sweep, retention audio path, DPDP erasure.

### Done in evening session (cont.)
- **Scoring pipeline (Phase 3) implemented** (Sonnet agent, verified): evidence assembly (§11.2) → 3 sequential runs × criteria (TODO spec-deviation: Batch API D15) → quote verification → median aggregation → report w/ LLM + deterministic fallback → app `scored`. 244 tests green. Worker restarted with new code.
- Per-requisition funnel endpoint (§12.1 #18) backed by `v_funnel` view — live-tested with real medians.
- Rate limits (§12.5) on claim/autosave/snapshots/proctor-events/inject/link-resolve — live-tested (60×200 then 429). Redis fixed-window, fails open.
- Admin "Interview (Text)" chat tab wired to the harness; web build+lint clean.

## Known deviations / notes
- `reports.review_decision`/`review_notes` are schema additions beyond SPEC §7 (Gemini; kept — useful). 0003 adds a CHECK + API Literal on decision.
- Migration `0001` is now frozen explicit DDL (2026-07-06); schema changes require a new migration.
- 0003 additions (organizations, catalog_entries, codes, 0–100 scores, etc.) supersede SPEC §7 in the touched areas; SPEC §3.6's "users owned by external auth" is obsolete — users/organizations live in our DB, WorkOS syncs into them.
- Web stack is React 19/Vite 8 (spec said React 18) — kept, no reason to downgrade.
- `GET /api/admin/funnel` is global; spec wants per-requisition `/requisitions/{id}/funnel`.
- Pydantic warning: field `schema` shadows BaseModel attr (name normative; harmless).
