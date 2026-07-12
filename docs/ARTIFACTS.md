# Interview Artifacts — where everything lives

This doc defines where every artifact produced by the candidate/interview
pipeline is stored, which database row points at it, who writes it, and who
reads it. It complements SPEC §6.3 (object storage) and §10 (proctoring).

## Two storage tiers

1. **Object storage (MinIO in dev, any S3-compatible store in prod).**
   All buckets are private. The browser never gets raw bucket access — the
   backend issues **presigned GET URLs** (`app/core/storage.py::presign_get`,
   TTL 600 s). URLs handed to a browser are signed against
   `KANDIDLY_S3_PUBLIC_ENDPOINT` (e.g. `http://localhost:9000`) because a
   presigned URL is host-bound; in-cluster access uses `KANDIDLY_S3_ENDPOINT`
   (`http://minio:9000`). Buckets are created by the `minio-init` one-shot in
   `infra/compose.yml`.

2. **Postgres.** Small/structured artifacts live directly in table columns
   (JSONB or text). Every S3 object that outlives a request is registered in
   the `stored_files` table (`bucket`, `key`, `mime`, `bytes`, `sha256`)
   and referenced by a foreign key from its owning row — the FK is the source
   of truth; orphan objects are garbage.

All monitoring artifacts (snapshots, recording, proctor events) are gated on
candidate consent (`app/domain/proctoring.py::require_consent` checks the
`consents` row written in the lobby).

## Artifact map

| Artifact | Storage | Key / column | DB pointer | Written by | Read by |
|---|---|---|---|---|---|
| Resume (original PDF/DOCX) | `kandidly-resumes` | `{application_id}/{file_id}.{ext}` (`storage.resume_key`) | `form_submissions.resume_file_id` → `stored_files` | `POST /api/candidate/applications/{id}/resume` | `parse_resume` job |
| Parsed resume | Postgres | `form_submissions.resume_markdown` (+ `resume_parse_status`) | — | `parse_resume` job (local pymupdf4llm/mammoth/tesseract, no LLM) | plan generation, agent bootstrap context, console |
| Candidate form input | Postgres | `form_submissions.answers` JSONB | — | autosave `PATCH /api/candidate/applications/{id}/form` | plan generation, admin application detail |
| Context enrichment (GitHub/site/blog digests) | Postgres | `form_submissions.enrichment` JSONB (+ `enrichment_status`) | — | `enrich_sources` job | plan generation, agent bootstrap context |
| Identity selfie | `kandidly-selfies` | `{application_id}/reference.webp` (`storage.selfie_key`) | `stored_files` row (also gates interview join) | lobby `POST /api/candidate/applications/{id}/selfie` | `identity_check` job (stub today) |
| Proctor snapshots | `kandidly-snapshots` | `{interview_id}/{epoch_ms}.webp` (`storage.snapshot_key`) | `proctoring_snapshots.file_id` → `stored_files`; CV results in `signal`, `analyzed`, `client_meta.vision` | interview-page capture loop → `POST /api/candidate/interviews/{id}/snapshots` | `analyze_snapshots` vision job, console review (presigned) |
| Proctor events (tab blur, camera off, …) | Postgres | `proctoring_events` rows | — | `POST /api/candidate/interviews/{id}/proctor-events`, agent relay `/internal` | report `proctoring_summary`, console integrity verdict |
| Integrity review (final verdict) | Postgres | `interviews.integrity_score` (0–100) + `interviews.integrity_review` JSONB `{summary, band, model, prompt_version, frames_reviewed, generated_at}` | — | `review_integrity` job (LLM over all frame analyses; chained by `analyze_snapshots`) | console review integrity chip + summary |
| Recording chunks (**transient**) | `kandidly-recordings` | `{interview_id}/chunks/{seq:05d}.{ext}` + `chunks/manifest.json` (`storage.recording_chunk_key` / `recording_manifest_key`) | none — deleted after finalize | browser MediaRecorder → `POST /api/candidate/interviews/{id}/recording/chunks` (+ `/recording/complete`) | `process_recording` job |
| Final recording | `kandidly-recordings` | `{interview_id}/audio.ogg` (`storage.recording_key`) | `interviews.audio_recording_id` → `stored_files`; peaks in `interviews.audio_waveform` JSONB `{version, peaks[], bins, duration_seconds}` | `process_recording` job (concat → ffmpeg transcode → peak extraction) | console review player (presigned) |
| Transcript | Postgres | `turns` rows (`seq`, `speaker`, `text`, `started_at`) | — | agent → `POST /internal/interviews/{id}/turns` | console review, scoring pipeline |
| Report HTML | `kandidly-reports` | `{interview_id}/report.html` (`storage.report_key`) | `reports.html_file_id` (**unused today** — reports render from JSON) | — (future) | — (future) |

## Recording pipeline (browser-side capture)

The interview audio is recorded **in the candidate's browser**: the interview
page mixes the local microphone track and the agent's remote audio track
through a Web Audio `MediaStreamDestination`, records it with `MediaRecorder`
(`audio/webm;codecs=opus`), and uploads ~15 s chunks as they are produced.
Chunks from a single MediaRecorder session byte-concatenate into one valid
stream (the header lives in chunk 0). On browsers without webm support
(Safari emits `audio/mp4`, whose sliced chunks are *not* concatenable) the
recorder buffers locally and uploads one final blob as chunk 0.

On end-of-interview the browser calls `/recording/complete`, which writes a
`chunks/manifest.json` (chunk count, client start time, mime) and enqueues
`process_recording`. `finalize_interview` also enqueues it with a 2-minute
delay as a safety net in case the browser died mid-call — the job is
idempotent (no-op once `audio_recording_id` is set). The job concatenates the
chunks, trims the head so t=0 ≈ `interviews.started_at` (aligning audio time
with transcript second-offsets), transcodes to mono 32 kbps Opus/OGG with
ffmpeg, extracts waveform peaks, writes `audio.ogg` + the `stored_files` row,
sets `audio_recording_id`/`audio_waveform`, and deletes the chunks.

## Lifecycle & retention

- `retention_sweeper` (daily cron, `app/jobs/sweepers.py`) deletes snapshots
  and selfies older than `KANDIDLY_RETENTION_DAYS_SNAPSHOTS` (default 180).
  Audio retention (`KANDIDLY_RETENTION_DAYS_AUDIO`, default 365) is a TODO in
  the sweeper.
- Recording chunks are deleted by `process_recording` immediately after the
  final artifact is written; they never outlive the finalize pass.
- `python -m app.db.seed --reset` truncates the database but does **not**
  empty MinIO — orphaned seed objects are harmless and overwritten on reseed.
