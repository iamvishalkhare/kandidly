---
name: verify
description: Drive Kandidly's candidate flow and console end-to-end in the local compose environment (headless browser + API), including the captcha-bypass form submit.
---

# Verifying Kandidly changes live

Everything runs against the podman compose stack (`cd infra && podman compose up -d`)
plus the web dev server in the `kandidly_web_1` container at http://localhost:5173.
Backend (http://localhost:8000) picks up host edits via `--reload` bind mount;
the arq worker does NOT auto-reload (`podman restart kandidly_worker_1` after job edits).

## Handles

- **Dev tokens**: `curl -s localhost:8000/api/public/dev-users` → per-user bearer
  tokens (admin + candidates). Frontend auth = localStorage `kandidly_token` +
  `kandidly_user` (JSON `{email, role, token}`), settable via Playwright
  `addInitScript`.
- **Playwright**: cached at `~/.npm/_npx/e41f203b7505f1fb/node_modules` — import by
  absolute path. Chromium flags for fake mic/cam:
  `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --autoplay-policy=no-user-gesture-required`.
- **Fresh candidate run**: `POST /api/public/dev-reset {token, email}` abandons the
  prior application, then `POST /api/candidate/i/{token}/claim`.

## Captcha-bypass form submit (reCAPTCHA is enforced locally)

1. `PATCH /api/candidate/applications/{id}/form` with required answers
   (usually `full_name`, `why_this_role`) — autosave is captcha-free.
2. Call `submit_form` directly inside the backend container (skips the Depends
   captcha). Gotchas: venv python is `/app/.venv/bin/python`, and `PYTHONPATH=/app/backend`
   is required when the script lives outside `/app/backend`:
   `podman exec -e PYTHONPATH=/app/backend kandidly_backend_1 /app/.venv/bin/python /tmp/submit.py <app_id> <user_id>`
   (script: SessionLocal + AuthUser from `app.core.security`, `await submit_form(...)`,
   `await db.commit()`).
3. **After** the commit, re-enqueue — the endpoint's own enqueue races the commit and
   the worker no-ops: `from app.core.queue import enqueue` (NOT app.jobs.queue);
   `enqueue('generate_plan', interview_id)` + `enqueue('enrich_sources', interview_id)`.

## Driving the lobby/interview UI

- Consent checkboxes are `sr-only` inputs — click the `label:has(input[type=checkbox])`.
- The selfie capture silently no-ops until the `<video>` has a frame: wait for
  `document.querySelector('video').videoWidth > 0` before clicking
  "Take verification photo".
- After consent the app state is `in_lobby`, and reloading the lobby jumps straight
  to the Ready step — a failed devices-step run needs a full dev-reset re-run.
- Join returns 202 until the plan job lands (LLM); the Ready step polls on its own.
  Agent greeting takes ~20–40s of TTS before captions appear.
- Console pages: set the admin token in localStorage, go to `/console/...`.
  Clipboard asserts need `permissions: ['clipboard-read', 'clipboard-write']`.

## Watch out

- Creating NEW requisitions via console API can 402 (`plan_limit`) — the dev org is
  over the free cap. Borrow one of the throwaway `API Test Engineer` requisitions
  (from the pytest API suite) via PUT instead, and restore its config after.
- Backend commits AFTER the response — poll instead of read-after-write in scripts.
- API test suite (host): `cd backend && KANDIDLY_API_TESTS=1 KANDIDLY_AUTH_DEV_MODE=true uv run pytest -q`
  (uses the live compose DB/redis; CI's S3 endpoint is deliberately dead, so tests
  must not touch object storage without the `stub_object_storage` fixture).
