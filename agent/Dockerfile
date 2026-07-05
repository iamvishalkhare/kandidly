# LiveKit Agents worker (SPEC §3.5 rule 7, §9).
# Built from repo root context (workspace-aware).
FROM docker.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace root (lockfile + workspace pyproject) + member pyproject for layer caching.
COPY pyproject.toml uv.lock ./
COPY agent/pyproject.toml agent/pyproject.toml

# Install deps only (no project source yet) for layer caching.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package kandidly-agent

# Copy agent source and install the project itself.
COPY agent/ agent/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package kandidly-agent

WORKDIR /app/agent

# `start` runs the worker; `download-files` (in entrypoint) prefetches model weights.
CMD ["uv", "run", "--package", "kandidly-agent", "python", "worker.py", "start"]
