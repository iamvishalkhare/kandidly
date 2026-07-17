#!/usr/bin/env bash
# Kandidly prod deploy — runs ON the server (docs/deploy-ec2.md). Idempotent;
# safe to re-run. This script is also the contract for the future CI deploy
# job: keep it self-contained (no assumptions beyond the repo checkout,
# docker/the compose plugin, and infra/.env.prod on the box).
#
#   pull → build → migrate (one-off container) → up -d → prune → health check
#
# Fails loudly (non-zero exit + diagnostics) if the stack comes up unhealthy.
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$INFRA_DIR")"
ENV_FILE="$INFRA_DIR/.env.prod"
COMPOSE=(docker compose -f "$INFRA_DIR/compose.prod.yml")

log()  { printf '\n== %s ==\n' "$*"; }
fail() { printf 'DEPLOY FAILED: %s\n' "$*" >&2; exit 1; }

# ── preflight ────────────────────────────────────────────────────────────────
docker compose version >/dev/null 2>&1 || fail "docker compose plugin not installed"
# The plugin check is client-side only; also verify we can reach the daemon
# (fails when docker.service is down or the caller's `docker` group membership
# isn't active yet — re-login after usermod, runbook §2).
docker info >/dev/null 2>&1 || fail "cannot talk to the Docker daemon (docker running? caller in the docker group?)"
[[ -f "$ENV_FILE" ]] || fail "$ENV_FILE missing — copy infra/.env.prod.example and fill it in"
[[ "$(stat -c %a "$ENV_FILE")" == "600" ]] || fail "$ENV_FILE must be chmod 600"

# Sourcing (rather than compose env_file alone) makes the values available to
# compose interpolation (VITE_API_BASE build arg) and to this script.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
: "${DOMAIN:?DOMAIN not set in .env.prod}"
: "${VITE_API_BASE:?VITE_API_BASE not set in .env.prod (baked into the web bundle)}"
: "${POSTGRES_USER:?POSTGRES_USER not set in .env.prod}"
: "${POSTGRES_DB:?POSTGRES_DB not set in .env.prod}"
# Interpolated into backend/worker as the S3 creds (compose.prod.yml) — empty
# values would silently break every upload with SignatureDoesNotMatch.
: "${MINIO_ROOT_USER:?MINIO_ROOT_USER not set in .env.prod}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD not set in .env.prod}"
# Empty (as opposed to absent) breaks agent /internal auth with 401s: the
# agent sends an empty X-Service-Token and the backend rejects it. Use
# `gh workflow run ops -f action=rotate-service-token` to set a fresh one.
: "${KANDIDLY_SERVICE_TOKEN:?KANDIDLY_SERVICE_TOKEN empty/not set in .env.prod}"

# ── pull ─────────────────────────────────────────────────────────────────────
log "git pull"
git -C "$REPO_DIR" pull --ff-only

# Deployed commit — interpolated into the backend container env
# (compose.prod.yml KANDIDLY_GIT_SHA) and echoed by /healthz, so the health
# check below can prove the new code is actually serving.
GIT_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
export GIT_SHA
log "deploying $GIT_SHA"

# ── build ────────────────────────────────────────────────────────────────────
log "build images"
"${COMPOSE[@]}" build

# ── migrate ──────────────────────────────────────────────────────────────────
log "start datastores"
"${COMPOSE[@]}" up -d postgres redis minio minio-init

log "wait for postgres"
for i in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    break
  fi
  [[ "$i" == 30 ]] && fail "postgres not ready after 60s"
  sleep 2
done

log "alembic upgrade head"
"${COMPOSE[@]}" run --rm backend uv run alembic upgrade head \
  || fail "migration failed — stack left as-is for inspection"

# ── up ───────────────────────────────────────────────────────────────────────
log "start full stack"
"${COMPOSE[@]}" up -d

log "prune old images"
docker image prune -f >/dev/null || true

# ── health check ─────────────────────────────────────────────────────────────
# Through local Caddy with real TLS (--resolve pins DNS to localhost, so this
# works even before/without public DNS propagation). First deploy needs a few
# seconds for the Let's Encrypt issuance, hence the retry loop.
log "health check"
healthy=0
for i in $(seq 1 45); do
  body="$(curl -fsS --resolve "api.${DOMAIN}:443:127.0.0.1" \
       "https://api.${DOMAIN}/healthz" 2>/dev/null || true)"
  # Require both healthy status AND the just-pulled sha — an old container
  # still answering must not pass the check.
  if grep -q '"status":"ok"' <<<"$body" && grep -q "\"sha\":\"$GIT_SHA\"" <<<"$body"; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != 1 ]]; then
  echo "last /healthz body: ${body:-<empty>} (expected sha $GIT_SHA)"
  "${COMPOSE[@]}" ps || true
  echo '--- backend logs ---'; "${COMPOSE[@]}" logs --tail 50 backend || true
  echo '--- caddy logs ---';   "${COMPOSE[@]}" logs --tail 50 caddy   || true
  fail "https://api.${DOMAIN}/healthz not healthy at $GIT_SHA after 90s"
fi

# SPA should answer with the index document.
curl -fsS --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/" >/dev/null \
  || fail "https://${DOMAIN}/ not serving"

log "deploy OK — api and app healthy"
