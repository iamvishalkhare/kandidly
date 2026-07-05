# Shared image for `backend` (uvicorn) and `worker` (arq) — differ only by command.
# SPEC §3.5 rule 7. Built from repo root context (workspace-aware).
FROM docker.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# System deps: resume text extraction (tesseract) + build headers for onnxruntime/insightface.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace root (lockfile + workspace pyproject) + member pyproject for layer caching.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml

# Install deps only (no project source yet) for layer caching.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package kandidly-backend

# Copy backend source and install the project itself.
COPY backend/ backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package kandidly-backend

WORKDIR /app/backend

EXPOSE 8000
CMD ["uv", "run", "--package", "kandidly-backend", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
