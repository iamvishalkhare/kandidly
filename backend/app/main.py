"""FastAPI application factory + router mounting (SPEC §5)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api import admin, candidate, internal, public
from app.core.config import settings
from app.core.errors import install_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kandidly Backend",
        version="0.1.0",
        description="AI voice interviewer — REST APIs, state machines, token issuance (SPEC §5).",
    )

    # CORS locked to the web origin (SPEC §16.7).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.base_url_web],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(app)

    app.include_router(public.router)
    app.include_router(candidate.router)
    app.include_router(admin.router)
    app.include_router(internal.router)

    # Prometheus metrics (SPEC §15).
    app.mount("/metrics", make_asgi_app())

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict:
        return {"status": "ok", "env": settings.env}

    return app


app = create_app()
