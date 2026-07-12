# Kandidly — Feature Roadmap: Ordering + Execution Prompts

## Context

Six features are queued: EC2 deployment, CI/CD, WorkOS auth, org settings + plans, invite-only interviews, and email integration. The goal of this plan is (a) an ordering where every step builds on the previous with no rework, and (b) a complete, copy-pasteable prompt per feature for executing it in a fresh session.

**Deliverable on approval:** save this ordering + the six prompts to `docs/roadmap-prompts.md` in the repo (no other code changes — features are executed later, one prompt at a time).

## Decisions locked (from Q&A)

| Area | Decision |
|---|---|
| Infra | Single EC2 **t3a.large**, full stack (Postgres/Redis/MinIO/backend/worker/agent/web) via **podman-compose**; domain will be purchased; **Caddy** for auto-TLS; **LiveKit Cloud** for prod voice |
| CI/CD | Build **on the EC2 box**; CI = ruff/mypy + pytest w/ real Postgres+Redis+migrations+seed + new API-level tests + web build/tsc/lint; deploy = **SSH + auto `alembic upgrade head`**, straight to prod on merge to main |
| Auth | **WorkOS AuthKit hosted UI** (Google OAuth, email+password, magic link); backend **exchanges callback for existing app JWT** (deps.py/Redis denylist untouched); **open signup + JIT provisioning**, existing users linked by email; candidates also via AuthKit (wired in feature 6); WorkOS sends its own auth emails (no app OTP) |
| Orgs | `org_memberships` join table + console org switcher; roles **Owner / Admin / Recruiter**; `organizations.plan` column (free/pro/max), **no payments yet** (superadmin assignment); org-creation cap = **highest plan among orgs the user owns** (Free 1 / Pro 3 / Max unlimited), new orgs start Free; orgs live **app-DB only** (no WorkOS org mirroring; `workos_org_id` stays for future SSO) |
| Invite-only | Per-requisition **public / invite_only** toggle, **flippable anytime**; **one shared URL for both modes**; invite-only gated by **email allowlist** (reuse `InviteLink kind='personal'`) + candidate WorkOS login with matching email |
| Email | **Resend**; launch emails: org member invite + candidate interview invite; jinja2 templates, sent via arq job, console/log transport in dev |

## Recommended order & why it avoids rework

**0. Prerequisite → 1. EC2 deploy → 2. CI/CD → 3. WorkOS auth → 4. Email (Resend) → 5. Organisations → 6. Invite-only interviews**

- **0 — Commit current work.** ~50 files of working-but-uncommitted changes (voice interview, enrichment, plan limits) must land on `main` before any CI/deploy automation exists, or the pipeline will deploy stale code.
- **1 before 2:** CI/CD needs a working server, a `compose.prod.yml`, and a `deploy.sh` to invoke. Feature 1 creates them manually once; feature 2 just automates calling them — zero rework.
- **2 before everything else:** every subsequent feature then ships through tested, auto-deployed merges. Building CI last would mean retrofitting tests around three big features.
- **3 before 4/5/6:** identity underpins orgs and invite-only. Doing WorkOS after orgs would mean rebuilding JIT provisioning and JWT claims twice. Critical rework-avoider baked into prompt 3: JIT signup **creates a fresh Organization per new user** (schema already supports it) instead of dumping everyone into the seeded default org — otherwise feature 5 would need a painful data untangling migration.
- **4 before 5:** org member invites need email sending. Email is a small, isolated integration — landing it first lets feature 5 ship complete (invite emails working on day one) instead of stubbing them.
- **5 before 6:** invite-only's console UX (toggle, invited-emails list) lives inside the org-scoped console with role checks; building it before roles/switcher exist would mean revisiting the same screens.
- **Cross-cutting rework guards:** JWT claim shape from feature 3 (`sub, email, role, org_id`) is exactly what feature 5 extends (org_id becomes "active org", role becomes per-membership) — call sites never change, only the resolver. Feature 6 reuses `InviteLink kind='personal'` + email column that already exist.

---

## Prompt 0 — Prerequisite (run first, small)

> Commit the current working tree to `main` in logical commits. Group roughly: candidate voice interview flow (agent/, LiveKit pieces, candidate pages), interview review enrichment (recording pipeline, proctoring, migrations 0006–0008), account modal + plan limits (auth.py, cache.py, plan.py, migration 0009), and infra/config changes. Run the backend test suite (`uv run pytest`) and web typecheck (`npm run build` in web/) before committing. Do not create a worktree; work directly on main. Push to origin when green.

---

## Prompt 1 — Production deployment on EC2

> Deploy Kandidly to production on a single EC2 instance. Context: monorepo with backend (FastAPI), worker (arq), agent (LiveKit voice agent), web (React/Vite SPA), plus Postgres 16, Redis 7, MinIO — all currently run locally via `infra/compose.yml` with podman-compose. Prod decisions already made: one **t3a.large** (Ubuntu 24.04 LTS), podman + podman-compose on the box, **Caddy** as reverse proxy with automatic Let's Encrypt TLS, domain `<DOMAIN>` (A records: `app.<DOMAIN>` → console+candidate SPA, `api.<DOMAIN>` → backend, `files.<DOMAIN>` → MinIO for presigned URLs), **LiveKit Cloud** for rooms + inference in prod (new prod project; agent container points at its URL/keys).
>
> Deliverables:
> 1. `infra/compose.prod.yml` — prod overlay: no source bind-mounts or dev servers; web built as static bundle via a multi-stage Dockerfile and served by Caddy; `restart: unless-stopped` everywhere; Caddy service added with a `Caddyfile` (app subdomain serves SPA with fallback to index.html; api subdomain proxies backend; files subdomain proxies MinIO — verify presigned-URL host/signature compatibility, set MINIO_SERVER_URL accordingly since the browser uploads recordings via presigned URLs).
> 2. `infra/.env.prod.example` — every required prod var documented: Postgres creds, Redis, MinIO creds + public endpoint, OpenRouter key, LiveKit Cloud URL/key/secret, reCAPTCHA prod keys, JWT secret, service token. Real `.env.prod` lives only on the server, chmod 600.
> 3. `infra/deploy.sh` (idempotent, runs on the server): `git pull`, `podman-compose -f compose.prod.yml build`, run `alembic upgrade head` in a one-off backend container, `podman-compose up -d`, prune old images, then curl a `/health` endpoint and fail loudly if unhealthy. This script is the contract the future CI deploy job will call — keep it self-contained.
> 4. `docs/deploy-ec2.md` — provisioning runbook: security group (22/80/443 only), elastic IP, DNS records, installing podman/podman-compose/git, cloning the repo to `/opt/kandidly`, systemd unit (or podman quadlet) so the stack survives reboots, EBS snapshot schedule for the data volumes, and a `pg_dump` cron to MinIO or local disk.
> 5. **Security stopgap:** auth is still the dev-token scheme (base64 JSON — forgeable). Until WorkOS lands, protect the console: Caddy `basicauth` on the console SPA routes and `/api/console/*`, `/api/admin/*`. Candidate routes (`/i/*`, `/api/candidate/*`, `/api/public/*`) stay open. Mark this clearly as temporary.
> 6. Seed: run the minimal prod seed (catalog entries + bootstrap admin user), not demo fixtures.
>
> Verify end-to-end on prod: create a requisition in the console, open the invite link in a browser, complete a short voice interview (LiveKit Cloud), confirm recording upload, enrichment, and the review page work. Document any env var whose prod value differs from dev in the runbook.

---

## Prompt 2 — CI/CD with GitHub Actions

> Build CI/CD for Kandidly. The repo deploys to a single EC2 box at `/opt/kandidly` which already has `infra/deploy.sh` (git pull → podman-compose build → alembic upgrade → up -d → health check). Decisions: images build on the EC2 box (no registry), merge to `main` deploys straight to prod, migrations auto-run.
>
> Deliverables:
> 1. `.github/workflows/ci.yml` — runs on every PR and push to `main`. Jobs:
>    - **backend-lint**: `ruff check` + `ruff format --check` + mypy (add mypy config if missing; keep strictness pragmatic).
>    - **backend-test**: Postgres 16 + Redis 7 as service containers; `alembic upgrade head`; load seed fixtures (`app/db/seed.py` / `seed_fixtures.py`); `uv run pytest`. LLM/LiveKit/Resend externals must be mocked or env-disabled — audit the suite for anything that hits the network and gate it.
>    - **api-tests** (part of backend-test or separate): write a new `backend/tests/api/` suite using httpx `AsyncClient` against the FastAPI app with the seeded DB, covering: console requisition CRUD + publish, invite-link resolve + claim, form submission, the interview lifecycle state transitions (mock the LLM planning/scoring jobs), and plan-limit enforcement (5-requisition cap, ER0402 hold). Use the existing dev-token auth to mint role tokens in tests.
>    - **web**: `npm ci`, `tsc --noEmit`, eslint, `vite build`.
> 2. `.github/workflows/deploy.yml` — on push to `main` only, after CI succeeds (use `workflow_run` on ci.yml completion or a `needs:` chain in one workflow). Steps: SSH to EC2 (`EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` repo secrets) and execute `/opt/kandidly/infra/deploy.sh`. Add `concurrency: group: prod-deploy, cancel-in-progress: false` so deploys serialize. On health-check failure the job must fail red.
> 3. Branch protection notes in the PR description: require CI green before merge to main.
>
> Keep existing `codeql.yml` untouched. Verify by pushing a trivial branch, watching CI pass, merging, and confirming the box redeploys and `/health` returns the new version (add a version/commit-SHA field to `/health` if absent).

---

## Prompt 3 — WorkOS AuthKit authentication

> Replace Kandidly's dev-token auth with WorkOS AuthKit for console users. Existing state: `users` table already has `workos_user_id` (unique, nullable) and orgs have `workos_org_id` (migration 0003); auth is JWT bearer verified in `backend/app/core/security.py` with a Redis logout denylist (`app/api/auth.py`, `core/deps.py:get_current_user`); dev tokens are base64 JSON accepted by `verify_jwt`. Decisions: **AuthKit hosted UI** (redirect flow) with Google OAuth + email/password + magic link enabled in the WorkOS dashboard; backend **exchanges the callback code for our own JWT** so `deps.py`, role guards, and the denylist stay untouched; **open signup with JIT provisioning**; orgs stay app-DB-only (do NOT create WorkOS organizations).
>
> Deliverables:
> 1. Backend (`workos` Python SDK): `GET /api/auth/login` → redirect to AuthKit authorization URL (state param for CSRF + optional return path); `GET /api/auth/callback` → exchange code, then JIT-provision: match by `workos_user_id`, else by email (link existing seeded/dev users by setting their `workos_user_id`), else create a new User. **Critical for the upcoming orgs feature: a brand-new console user gets their own new Organization row** (name derived from email/display name, refine later) with `users.org_id` pointing at it — do not attach new signups to the seeded default org. Then mint the existing app JWT (claims: sub, email, role, org_id — same shape as today) and hand it to the SPA (redirect to a `/auth/callback` frontend route with the token, or set it via a short-lived exchange code; pick the simpler robust option and document it). Config: `WORKOS_API_KEY`, `WORKOS_CLIENT_ID`, `WORKOS_REDIRECT_URI` in `core/config.py` + both env examples.
> 2. Dev-token retirement: `verify_jwt` accepts dev tokens **only when `settings.env == "dev"`** so local dev and the CI test suite keep working; prod rejects them. Remove the Caddy basicauth stopgap from feature 1 (update Caddyfile + runbook).
> 3. Frontend: replace the dev login with a "Sign in" that hits `/api/auth/login`; add the callback route that stores the JWT where the console already expects it (`web/src/lib/consoleApi.ts`); logout keeps calling `/api/auth/logout` (denylist) and additionally clears local state. Handle the invited/suspended user statuses with a clean error screen.
> 4. New-signup role: default `admin` of their own fresh org (they're its only member until the orgs feature adds real roles).
> 5. Candidates: do NOT wire candidate AuthKit login yet — that ships with invite-only interviews. Candidate anonymous claim flow must keep working unchanged.
>
> Tests: JIT provisioning paths (new user / email-link / repeat login), dev-token rejection when env != dev, logout denylist still effective. Verify manually in dev against a real WorkOS test project: fresh Google signup → lands in console with own org; existing seeded admin logs in via magic link → linked, sees existing data.

---

## Prompt 4 — Email integration (Resend)

> Add transactional email to Kandidly via **Resend**. Emails are dispatched from arq background jobs (worker already exists: `backend/app/jobs/worker.py`). Launch scope: (a) org member invite, (b) candidate interview invite — both consumed by upcoming features, so build the sending machinery + templates now with a way to exercise them.
>
> Deliverables:
> 1. `backend/app/core/email.py`: thin client with a transport abstraction — `resend` transport (RESEND_API_KEY) and a `console` transport that logs the rendered email in dev/tests (selected via settings; default console when no API key). Retries with backoff on 5xx/429 via the arq job wrapper.
> 2. `backend/app/jobs/email.py`: `send_email` arq task (to, template, context); enqueue helper for API code. Failures logged loudly, no crash loops.
> 3. Templates in `backend/app/emails/`: jinja2, each with HTML + plain-text part, shared base layout (logo/name placeholder, footer). Two templates: `org_invite` (inviter name, org name, accept URL, expiry) and `candidate_invite` (org/company name, role title, interview URL, expiry note). Keep copy neutral and short.
> 4. Config: `RESEND_API_KEY`, `EMAIL_FROM` (e.g. `Kandidly <no-reply@<DOMAIN>>`), `EMAIL_TRANSPORT` in config + env examples. Document Resend domain verification (DKIM/SPF DNS records) in the deploy runbook.
> 5. A superadmin-only test endpoint or CLI script that renders+sends a given template to a given address, for smoke-testing prod deliverability.
>
> Tests: template rendering (both parts, all context vars), console transport capture, enqueue path. Verify in dev via console transport; verify in prod by sending both templates to your own address through the test endpoint after DNS verification.

---

## Prompt 5 — Organisation settings, memberships, and plans

> Build multi-org support for Kandidly. Existing state: `organizations` (id, name, slug, settings JSONB, plan-less) and `users.org_id` single-FK membership; roles are global (`admin`/`recruiter`); free-plan quotas live in `core/config.py` (`free_plan_max_requisitions=5`, `free_plan_max_interviews=25`, `hold_at=50`) enforced in `app/domain/plan.py` + `app/api/console.py`; every domain table is already org-scoped; WorkOS AuthKit login mints app JWT with claims (sub, email, role, org_id); Resend email machinery exists (`core/email.py`, `jobs/email.py`, `org_invite` template). Orgs are app-DB-only (no WorkOS org sync).
>
> Decisions: membership join table + org switcher; roles **owner/admin/recruiter** per org (owner: plan + delete org + everything; admin: manage members + everything below; recruiter: requisitions/interviews only); `organizations.plan` ∈ free/pro/max with **no payments** (superadmin script/endpoint flips it); org-creation cap = highest plan among orgs the user **owns**: free→1, pro→3, max→unlimited; new orgs always start free.
>
> Deliverables:
> 1. Migration: `org_memberships` (id, org_id FK, user_id FK, role check owner/admin/recruiter, created_at, UNIQUE(org_id,user_id)); `org_invites` (id, org_id, email, role, token unique, invited_by, expires_at, accepted_at, revoked_at); `organizations.plan` (text, default 'free', check). Backfill: one membership per existing user from `users.org_id` (existing org creators/admins → owner). Keep `users.org_id` as "last active org" (rename semantics in comments) rather than dropping it.
> 2. Auth/session: JWT org claims now mean **active org**; role in JWT = membership role for that org. `GET /api/console/me` returns memberships list; `POST /api/console/orgs/switch` validates membership and re-mints the JWT. Update `require_role` guards so console routes authorize against the active org's membership role; add `require_org_role('owner'|'admin'|...)` where member management/plan endpoints need it. JIT signup (from the WorkOS feature) now creates the org + an **owner** membership.
> 3. Plans: generalize `domain/plan.py` to per-plan quota config (`plan_quotas = {free: {reqs:5, interviews:25, hold:50}, pro: {...}, max: {...}}` — put pro/max placeholder numbers in config, easily tuned). Enforce org-creation cap on `POST /api/console/orgs` (count orgs where user has owner membership vs best owned plan). Superadmin plan-assignment endpoint guarded by the existing service token or a superadmin flag.
> 4. Invites: `POST /api/console/orgs/{id}/invites` (admin+): creates invite, enqueues `org_invite` email with accept URL `app.<DOMAIN>/join/<token>`; accept flow: user logs in via WorkOS (existing flow), then `POST /api/console/invites/{token}/accept` creates the membership (email on invite must match logged-in email, case-insensitive); revoke + resend endpoints; expiry (7 days).
> 5. Frontend: org switcher in `web/src/pages/console/ConsoleLayout.tsx` (current org name, dropdown of memberships, "create organisation" gated by the cap with an upgrade nudge when blocked); Organisation Settings page: org name edit, plan badge, members table (role change by admin+, remove, owner transfer by owner), pending invites (invite by email+role, revoke, resend); `/join/<token>` accept page (prompts login first if logged out). Update the account modal so plan display moves from account to per-org.
> 6. Edge cases to handle: last-owner protection (can't demote/remove/leave as sole owner), invited email belonging to an existing user in another org (fine — multi-org), removing a member with active requisitions (keep data, `created_by` stays), deleting an org (soft, owner-only, blocked if it's the user's only org).
>
> Tests: membership backfill migration, switch-org re-mint + guard enforcement (recruiter can't invite; admin can't change plan), creation cap per plan tier, invite accept happy path + email mismatch + expiry, last-owner protection, per-org quota isolation (org A's requisitions don't count against org B). Verify manually: two browsers, invite flow end-to-end with a real second email, switcher isolates data correctly.

---

## Prompt 6 — Invite-only interviews

> Add a per-requisition access-mode toggle: **public** (anyone with the link) vs **invite_only** (only invited emails, after logging in). Existing state: `InviteLink` supports `kind='open'` (shared) and `kind='personal'` (has `email`) with a claim flow; requisitions have `interview_config` JSONB + status lifecycle; candidate flow is anonymous claim via `/i/:token` (`web/src/pages/candidate/Landing.tsx`, `Form.tsx`, `api/candidate.py`, `api/public.py`); WorkOS AuthKit is live for console users (`/api/auth/login|callback` minting app JWTs); org-scoped console with roles exists; Resend `candidate_invite` template exists.
>
> Decisions: **one shared URL for both modes** — the toggle changes gating, not the link; flippable anytime including mid-campaign (existing in-flight interviews finish; new visitors see the current mode); invite-only gate = **email allowlist**: recruiter adds invited emails, candidate must authenticate via **WorkOS AuthKit (candidate role)** and their verified email must be on the list; uninvited/mismatched users get a clear blocked screen.
>
> Deliverables:
> 1. Schema: `requisitions.access_mode` (text, default 'public', check public/invite_only) via migration. Invited emails = `InviteLink kind='personal'` rows for the requisition (email required, reuse existing columns; token unused for gating but keep it valid as a direct link).
> 2. Candidate auth: extend the WorkOS flow for candidates — `GET /api/auth/candidate/login?next=/i/<token>` → AuthKit; callback JIT-provisions role='candidate' users (org-less, per the users table comment) and mints the candidate-scoped JWT the interview flow already uses; do not let candidate JWTs access console routes (already role-guarded — add a test).
> 3. Gating in the landing/claim path (`api/public.py` resolve + `api/candidate.py` claim): if requisition is invite_only → resolve returns `auth_required` state; after login, claim succeeds only if the JWT email matches an unrevoked personal InviteLink for that requisition (case-insensitive); enforce again server-side at claim AND at interview start (mode may flip between page load and start). Public mode: existing anonymous flow byte-for-byte unchanged. Personal-link visits with matching token skip nothing security-wise — same email check against the logged-in user.
> 4. Console UI: toggle on the requisition (builder + detail), with copy explaining both modes; "Invited candidates" panel (visible when invite_only, or always with the list driving both modes): add single/bulk emails (textarea paste), each add creates the personal InviteLink and enqueues the `candidate_invite` Resend email with the shared URL; show status per invitee (invited / attempted / completed by joining against applications), resend + revoke actions.
> 5. Candidate UX (`Landing.tsx`): invite_only + logged out → "This interview is invite-only — sign in with the email that received the invitation" + sign-in button; logged in with non-invited email → blocked screen showing the current email with a switch-account (logout+login) action; invited → normal form/interview flow, application bound to their user + email.
> 6. Edge cases: same email invited twice (idempotent upsert), revoke after attempt started (in-flight continues, no new claim), attempt limits still enforced via existing use_count/max_uses semantics, public→invite_only flip locks out new anonymous visitors instantly (verify resolve honors it), and email comparison is normalized (trim/lowercase).
>
> Tests: resolve/claim matrix — (mode × {anonymous, logged-in invited, logged-in uninvited, revoked}); mid-flight mode flip; candidate JWT rejected on console routes; invite panel CRUD + email enqueue. Verify manually end-to-end: invite your own second email, receive the Resend email, sign in via AuthKit as candidate, complete a voice interview; then flip the req to public and confirm anonymous access resumes.

---

## Verification of this plan's deliverable

After approval: write `docs/roadmap-prompts.md` containing the ordering rationale and the seven prompts above (0–6), commit nothing else. Each prompt is then executed in its own future session in the stated order.
