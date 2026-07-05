# Kandidly — System Build Specification (anchor)

**Version:** 1.1 | **Status:** Approved for implementation | **Owner:** Vishal (zState.ai)

> The full normative v1.1 specification is the governing document for this repo.
> This file is the in-repo anchor: paste the complete v1.1 spec text here (it is
> long) so contributors have the authoritative reference. Below is the durable
> summary that drives day-to-day implementation. Naming is normative (SPEC §0.5).

## Locked decisions (do not reinterpret)

| # | Decision |
|---|----------|
| D1 | Cascading voice pipeline STT → LLM → TTS (no speech-to-speech). |
| D2 | Candidate answers spoken only, stored as text; session audio also stored (S3). |
| D3 | Kandidly is audio-only (no avatar). |
| D4 | English only (`en`). |
| D5 | Proctoring = browser events + jittered photo snapshot every 5–10s + audio signals + post-hoc identity check. No continuous video. |
| D6 | Hard cap 30 min active interview time (clock pauses on disconnect). |
| D7 | Recruiters observe live (hidden) and inject questions. |
| D8 | Everything starts from a requisition; publish → shareable link → KYI form → lobby → interview. |
| D9 | PostgreSQL 16 (JSONB + relational); S3 for binaries. No Mongo/vector DB. |
| D10 | Form templates + rubrics immutable once published; edits = new version. |
| D11 | One attempt per candidate per requisition; one rejoin within grace. |
| D12 | Orchestration: LiveKit (rooms + Agents, Python worker). |
| D13 | Offline LLM work uses pydantic-ai structured outputs. No LangGraph. |
| D14 | Realtime brain = one LLM call/turn with a control-prefix protocol (§8.7). |
| D15 | Scoring = 3 runs → median via provider Batch API, disagreement flagging. |
| D16 | UUIDv7 PKs in app layer; enum-likes = text + CHECK. |
| D17 | Containers run on Podman (rootless), engine-agnostic `infra/compose.yml`. |
| D18 | uv is the Python package manager. Workspace at repo root (`backend`, `agent` members); `uv.lock` committed; `uv sync`/`uv run` everywhere (local + container). |

## Build order (SPEC §19) and phase gates

```
T01 infra  T02 backend skeleton  T03 schema+seed  T04 states  T05 forms
T06 links+claim  T07 resume  T08 rubric  T09 plan  T10 llm+prompts  T11 control+harness
── Phase 1 gate ──
T13 agent worker  T14 lobby+room UI  T15 egress+heartbeat+sweepers
── Phase 2 gate ──
T16 finalize+scoring  T17 report+review UI
── Phase 3 gate ──
T18 proctor+consent  T19 identity_check  T20 observer+injection
── Phase 4 gate ──
T21 analytics+cost  T22 edge-case sweep E1–E20 + load/latency
```

Phases: 1 text-mode skeleton, 2 voice, 3 scoring+reports, 4 proctoring+observer,
5 analytics+hardening. See `docs/STATUS.md` for current progress.

## Interpretation rules (SPEC §0)
- MUST/SHOULD/MAY per RFC-2119.
- `[VERIFY-DOC]` = verify external API against official docs at build time; documented API wins.
- `[ASSUMPTION]` = implement as written, keep configurable.
- Do not invent scope; add `TODO(spec-gap): <question>` at the site when behavior is unspecified.
- Names (tables/columns/states/events/env vars/JSON fields) are normative.
- Prompts live under `backend/app/llm/prompts/{name}_{version}.md`, versioned.

_Replace this section boundary with the full v1.1 text when convenient; the
implementation already follows the complete spec, not just this summary._
