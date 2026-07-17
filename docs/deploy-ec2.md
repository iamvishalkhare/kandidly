# Kandidly — single-EC2 production deployment runbook

Prod runs the whole stack on one EC2 instance with Docker Compose:
Caddy (TLS + routing + the temporary console gate), backend (FastAPI), worker
(arq), agent (LiveKit voice), Postgres 16, Redis 7, MinIO. Rooms and realtime
STT/LLM/TTS come from **LiveKit Cloud** (a dedicated prod project).

`DOMAIN` below is the base hostname the SPA is served at — for this install
`kandidly.vishalkhare.com`, with `api.` and `files.` nested one level deeper.

```
                    ┌──────────────────────── EC2 t3a.large ────────────────────────┐
 browser ── 443 ──▶ │ Caddy ── DOMAIN       → SPA bundle (/srv, baked in the image) │
                    │       ── api.DOMAIN   → backend:8000 ──┬─ postgres:5432       │
                    │       ── files.DOMAIN → minio:9000     ├─ redis:6379 ◀─ worker│
                    │                                        └─ minio:9000 ◀─ agent ┼─▶ LiveKit Cloud
                    └────────────────────────────────────────────────────────────────┘
```

Files that make up the deployment:

| File | Role |
|---|---|
| `infra/compose.prod.yml` | standalone prod stack (no bind mounts, no dev servers) |
| `infra/Caddyfile.prod` | TLS, subdomain routing, **temporary console gate** |
| `infra/.env.prod.example` | template for `infra/.env.prod` (server-only, chmod 600) |
| `infra/deploy.sh` | the deploy contract: pull → build → migrate → up → health check |
| `web/Dockerfile.prod` | multi-stage: Vite build → static bundle in the Caddy image |
| `backend/app/db/seed_prod.py` | minimal one-time seed (catalog + bootstrap admin) |

---

## 1. Provision the instance

1. **EC2**: t3a.large, Amazon Linux 2023, 30 GB+ gp3 root volume (images +
   media live here; MinIO data grows with recordings/snapshots). The default
   user is `ec2-user` (UID 1000).
2. **Security group** (inbound): 22/tcp (ideally restricted to your IP),
   80/tcp (ACME + redirect), 443/tcp. Optionally 443/udp for HTTP/3 — skip it
   if you want the literal "22/80/443 only" posture; Caddy falls back to h2.
   Outbound: allow all (LiveKit Cloud, OpenRouter, Let's Encrypt, GitHub).
3. **Elastic IP**: allocate and associate, so DNS survives stop/start.
4. **DNS** — three A records to the elastic IP: `DOMAIN`, `api.DOMAIN`,
   `files.DOMAIN`. No wildcard needed. For `kandidly.vishalkhare.com` on
   Squarespace: Domains → vishalkhare.com → DNS → Custom records, add:

   | Host | Type | Data |
   |---|---|---|
   | `kandidly` | A | \<elastic IP\> |
   | `api.kandidly` | A | \<elastic IP\> |
   | `files.kandidly` | A | \<elastic IP\> |

   Wait for resolution (`dig +short kandidly.vishalkhare.com`) before first
   deploy — Let's Encrypt must reach port 80/443 by name.

## 2. Prepare the box

> **Note:** AL2023 dropped `podman`/`buildah`/`skopeo` from its default repo
> at some point after early 2026 (confirmed on an AMI dated 2026-07;
> `dnf search podman` returns nothing, while `docker`/`containerd`/`nerdctl`
> are present). This runbook uses Docker (rootful) instead — if your AMI
> still has `podman` available, that path is simpler (no daemon, no group
> membership needed) but isn't documented here anymore.

```bash
sudo dnf install -y docker git cronie
sudo systemctl enable --now docker
# ec2-user needs docker group membership to run `docker`/`docker compose`
# without sudo — but that only takes effect on a fresh login, so verify with
# sudo here rather than assuming it's already active in this shell:
sudo usermod -aG docker ec2-user
sudo docker compose version

# crond is not enabled by default on AL2023 (needed for the pg_dump cron, §6):
sudo systemctl enable --now crond
```

If `sudo docker compose version` fails, the compose plugin isn't bundled with
this `docker` package build — install it system-wide (no separate dnf package
was found for it on this AMI), so it's visible to both `sudo docker` and
ec2-user's own `docker` once group membership is active:

```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

Same story for `docker buildx` — `compose build` shells out to it, and if it's
missing or older than 0.17.0 you'll see `compose build requires buildx 0.17.0
or later`. Unlike the compose binary above, buildx's release filenames embed
the version, so resolve the latest tag via the GitHub API first:

```bash
BUILDX_VERSION=$(curl -fsSL https://api.github.com/repos/docker/buildx/releases/latest | grep -oP '"tag_name": "\K[^"]+')
sudo curl -fsSL "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-amd64" \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
docker buildx version
```

(AL2023 runs SELinux in permissive mode by default; the compose files already
carry `:z` labels on bind mounts, so enforcing mode also works — Docker
honors the same SELinux label flags as podman did.)

**Log out and back in now** (or run `newgrp docker`) so ec2-user's `docker`
group membership is active in your shell before continuing — §4's
`./infra/deploy.sh` runs `docker compose` directly, without `sudo`.

Clone the repo:

```bash
sudo mkdir -p /opt/kandidly && sudo chown ec2-user:ec2-user /opt/kandidly
git clone https://github.com/<you>/kandidly.git /opt/kandidly
```

(Private repo: use a fine-grained read-only deploy token or deploy key. The
future CI job will push over the same remote and call `infra/deploy.sh`.)

## 3. Configure `infra/.env.prod`

```bash
cd /opt/kandidly
cp infra/.env.prod.example infra/.env.prod
chmod 600 infra/.env.prod
```

Fill in every value — the template documents each one. Highlights:

- `DOMAIN`, `ACME_EMAIL`, `VITE_API_BASE=https://api.DOMAIN`
- Random secrets: `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD` (=
  `KANDIDLY_S3_SECRET_KEY`), `KANDIDLY_SERVICE_TOKEN`, `CONSOLE_GATE_COOKIE`
  — all via `openssl rand -hex 32`. Remember `KANDIDLY_DATABASE_URL` embeds
  the Postgres password literally (no `${}` expansion in env files).
- `CONSOLE_GATE_HASH`:
  `docker run --rm docker.io/library/caddy:2.10 caddy hash-password --plaintext 'YOUR-PASSWORD'`
- LiveKit Cloud **prod project** URL/key/secret; enable the three
  `KANDIDLY_INFERENCE_*` models on that project (agent joins but stays silent
  if a model id isn't enabled).
- `KANDIDLY_OPENROUTER_API_KEY` — without it, resume extraction, question
  planning, scoring, vision proctoring, and integrity review all stall.
- reCAPTCHA v3 **prod** keys for the `DOMAIN` origin.

### Env vars whose prod value differs from dev

| Var | dev | prod |
|---|---|---|
| `KANDIDLY_ENV` | `dev` | `prod` (hides staff dev-users from ungated callers) |
| `KANDIDLY_S3_PUBLIC_ENDPOINT` | `http://localhost:9000` | `https://files.DOMAIN` |
| `MINIO_SERVER_URL` | unset | `https://files.DOMAIN` (must match the line above) |
| `MINIO_BROWSER` | on (console at :9001) | `off` |
| `KANDIDLY_BASE_URL_WEB` | `http://localhost:5173` | `https://DOMAIN` (also the CORS allowlist) |
| `VITE_API_BASE` | `http://localhost:8000` | `https://api.DOMAIN` (baked at build time) |
| `KANDIDLY_SERVICE_TOKEN` | `dev-service-token-change-me` | random 64-hex |
| `KANDIDLY_RECAPTCHA_*` | empty (fail-open) | prod site+secret keys (enforced) |
| `KANDIDLY_LIVEKIT_*` | dev LiveKit project | dedicated prod LiveKit Cloud project |
| `POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD` | `kandidly` / `kandidly-secret` | random |
| `KANDIDLY_AUTH_DEV_MODE` | `true` | **still `true`** — see §7 |

## 4. First deploy

```bash
cd /opt/kandidly
./infra/deploy.sh
```

The script is idempotent and is the same entrypoint CI will call later. It
fails loudly (with `ps` + logs) if `https://api.DOMAIN/healthz` doesn't come
up. First run takes a while: image builds + Let's Encrypt issuance.

Then the **one-time prod seed** (catalog entries + bootstrap admin + optional
shared test candidate — *not* the dev demo fixtures):

```bash
docker compose -f infra/compose.prod.yml run --rm backend \
    uv run python -m app.db.seed_prod
```

It prints the bootstrap admin's dev token **once** — store it in your password
manager (emergency/API access; day-to-day you log in through the console UI).

## 5. Survive reboots

No custom unit needed. `docker.service` was already enabled in §2, and every
service in `compose.prod.yml` carries `restart: unless-stopped` — Docker
restarts containers with that policy whenever the daemon comes back up
(reboot or `systemctl restart docker`), as long as they weren't manually
stopped beforehand. This also covers ordinary crash-restarts while the stack
is up (e.g. the arq worker's known exit-on-redis-restart).

Verify with a reboot: `sudo reboot`, then `docker ps` after logging back in —
all services should be `Up`.

## 6. Backups

**EBS snapshots** — cover all named volumes (Postgres, MinIO, Redis, certs)
at the block level. In the AWS console: Data Lifecycle Manager → create a
snapshot policy targeting the instance's volumes, daily at 03:00 UTC, retain 7.
Tag the volume (e.g. `Backup=kandidly`) and target that tag.

**pg_dump** — logical backups survive volume-level corruption and are easy to
restore selectively. Nightly cron on the box, shipped to the `kandidly-backups`
MinIO bucket (created by minio-init) and kept 14 days locally:

```bash
mkdir -p /opt/kandidly/backups
crontab -e   # as ec2-user; add:
```

```cron
15 3 * * * docker compose -f /opt/kandidly/infra/compose.prod.yml exec -T postgres pg_dump -U kandidly -Fc kandidly > /opt/kandidly/backups/kandidly-$(date +\%F).dump && docker run --rm --network kandidly_default -v /opt/kandidly/backups:/backups:z --env-file /opt/kandidly/infra/.env.prod quay.io/minio/mc:RELEASE.2025-04-08T15-39-49Z sh -c 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" && mc cp /backups/kandidly-$(date +\%F).dump local/kandidly-backups/' && find /opt/kandidly/backups -name '*.dump' -mtime +14 -delete
```

(The network is still `kandidly_default` — Compose v2 keeps underscores for
network/volume names, only container names switched to hyphens, which is why
`exec -T postgres` via the compose file is used instead of a hardcoded
container name.)

Restore drill (do this once): `pg_restore -U kandidly -d kandidly --clean <dump>`
into a scratch database and sanity-check row counts.

## 7. ⚠ TEMPORARY security stopgap (until WorkOS)

App auth is still the **dev-token scheme**: an unsigned base64 JSON payload
anyone can forge (`KANDIDLY_AUTH_DEV_MODE=true` in prod). Until WorkOS lands,
the Caddy edge is the actual security boundary:

- `DOMAIN/console*` → **basicauth** (`CONSOLE_GATE_USER`/`_HASH`). Passing
  it sets a domain-wide `HttpOnly` gate cookie (`CONSOLE_GATE_COOKIE`).
- `api.DOMAIN/api/admin/*` (includes `/api/admin/console/*`) → requires the
  gate cookie; plain basicauth also accepted for curl/CI. Plain basicauth on
  these paths alone can't work for the SPA — the app already uses the
  `Authorization` header for its Bearer token, hence the cookie.
- `/api/public/dev-users` → staff (admin/recruiter) tokens are only included
  when Caddy asserts the gate (`X-Console-Gate`, stripped from all inbound
  requests). Candidate accounts stay listed — the landing-page picker needs
  them. `/api/public/dev-reset` is gated.
- `/internal/*`, `/metrics`, `/docs`, `/redoc`, `/openapi.json` → 404 at the
  edge; only the compose network reaches them.
- Candidate surfaces stay open: `/i/*`, `/apply/*`, `/api/candidate/*`,
  `/api/public/*` (guarded by rate limits + reCAPTCHA + link validity).

**Residual risk, accepted knowingly:**

- Candidate-role tokens are self-forgeable; candidate endpoints validate
  ownership by user id, so the blast radius is a candidate's own application.
- Anyone with an invite link can interview as the shared test-candidate
  account. Real multi-candidate hiring needs per-candidate accounts —
  don't share invite links beyond controlled tests until WorkOS.
- The bootstrap admin token printed by seed_prod is a permanent credential
  (until logout-revoked). Treat it like a root password.

**Rotation:** change `CONSOLE_GATE_COOKIE`/`CONSOLE_GATE_HASH` in `.env.prod`,
then `docker compose -f infra/compose.prod.yml up -d caddy`. Remove this whole
section (and the Caddyfile gate block, the `dev_users` gating in
`backend/app/api/public.py`, and `KANDIDLY_AUTH_DEV_MODE`) when WorkOS lands.

## 8. End-to-end verification (run after every first-class deploy)

1. `https://api.DOMAIN/healthz` → `{"status":"ok","env":"prod"}` (deploy.sh
   already asserted this).
2. `https://DOMAIN/console` → basicauth prompt → login screen lists the
   bootstrap admin (and **no** staff accounts when opened in a private window
   without basicauth).
3. Console → create a requisition (template + rubric + deploy), copy the
   invite link.
4. Open the invite link in a private window: landing resolves, pick the test
   candidate, complete the form (resume upload exercises MinIO + the parse
   job; requires reCAPTCHA to pass), reach the lobby.
5. Lobby → camera/mic check → start the interview: the agent should greet you
   within ~10s (LiveKit Cloud prod project; if it joins silently, check the
   `KANDIDLY_INFERENCE_*` models are enabled on the project).
6. Speak through a short interview; confirm captions/timer, then let it wrap.
7. Review page (console): recording plays (browser fetches a presigned
   `https://files.DOMAIN/...` URL — this validates MinIO signature/host
   config), transcript present, scoring completes ("evaluating" clears within
   a few minutes; needs the OpenRouter key), proctoring snapshots + integrity
   verdict appear.
8. `docker compose -f infra/compose.prod.yml logs --tail 50 worker agent` —
   no error loops.

## 9. Day-2 operations

- **Deploy an update**: push to main, then on the box: `./infra/deploy.sh`.
- **Rollback**: `git -C /opt/kandidly reset --hard <last-good-sha> && ./infra/deploy.sh`
  (migrations are forward-only; roll forward when a migration is involved).
- **Logs**: `docker compose -f infra/compose.prod.yml logs -f --tail 100 <svc>`.
- **Known gotcha** (from dev, still true in prod): `up -d` that recreates
  redis kills the arq worker's blocking connection; `restart: unless-stopped`
  brings it back automatically — verify with `docker ps`.
- **Certificates**: Caddy renews automatically; state persists in the
  `caddydata` volume. Don't delete it, or you'll re-issue against Let's
  Encrypt rate limits.
- **Disk**: `docker system df` and `df -h /` monthly; deploy.sh prunes
  dangling images on every run.

## 10. CI deploy on push to main (GitHub Actions + SSM)

Two workflows. `.github/workflows/ci.yml` runs on every PR and push to
`main`: backend lint (ruff + mypy), backend tests against Postgres 16 + Redis
7 service containers (migrated, seeded, including the `tests/api` suite over
the real app), and the web lint + typecheck + build. `.github/workflows/
deploy.yml` fires via `workflow_run` when CI **succeeds on `main`** and runs
`infra/deploy.sh` on the box via **AWS SSM send-command** — no inbound SSH
(the security group stays closed to GitHub's runners), no long-lived AWS keys
(GitHub OIDC). Deploys serialize (`concurrency: prod-deploy`) and go red when
the post-deploy health check can't see the new commit's sha on `/healthz`.
Deploys never touch data: named volumes persist, migrations are in-place, and
nothing in CI seeds.

One-time setup:

1. **Instance role** (lets SSM manage the box): IAM → create role for EC2 with
   the `AmazonSSMManagedInstanceCore` managed policy → attach to the instance
   (EC2 → Actions → Security → Modify IAM role). Amazon Linux 2023 ships the
   SSM agent; verify with `systemctl status amazon-ssm-agent` on the box.

2. **GitHub OIDC provider** (IAM → Identity providers → Add):
   provider `token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.

3. **Deploy role** the workflow assumes. Trust policy (locks it to this repo's
   main branch):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
         "StringLike": { "token.actions.githubusercontent.com:sub": "repo:iamvishalkhare/kandidly:ref:refs/heads/main" }
       }
     }]
   }
   ```

   Permissions policy (send commands to this one instance only):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "ssm:SendCommand",
         "Resource": [
           "arn:aws:ec2:<REGION>:<ACCOUNT_ID>:instance/<INSTANCE_ID>",
           "arn:aws:ssm:<REGION>::document/AWS-RunShellScript"
         ]
       },
       { "Effect": "Allow", "Action": "ssm:GetCommandInvocation", "Resource": "*" }
     ]
   }
   ```

4. **GitHub repo secrets** (Settings → Secrets and variables → Actions):
   `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `EC2_INSTANCE_ID`.

5. If the repo is private, the box's `git pull` needs read access: add a
   deploy key (`ssh-keygen -t ed25519` on the box, public key → repo Settings
   → Deploy keys, read-only) — CI only *triggers* the pull; the box does it.

Notes: the workflow queues concurrent pushes (`concurrency: deploy-prod`) so
two deploys never race, and the `production` environment lets you add manual
approval or branch protections later. SSM runs commands as root, so the
workflow wraps deploy.sh in `runuser -l ec2-user` — that keeps the repo
checkout and Docker Compose runs under ec2-user's ownership and its `docker`
group membership (§2), rather than leaving root-owned files behind.
