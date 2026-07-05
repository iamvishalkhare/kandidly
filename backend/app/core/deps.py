"""FastAPI dependencies (SPEC §3.6, §5, §12). Auth resolution, role guards,
service-token auth, and the DB session."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import AuthUser, Role, verify_jwt, verify_service_token
from app.db.session import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:  # pragma: no cover
    async for s in get_session():
        yield s


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("unauthorized", "Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """SPEC §3.6 — resolve the AuthUser from the Authorization header."""
    return verify_jwt(_bearer(authorization))


def require_role(*roles: Role) -> Callable[[AuthUser], AuthUser]:
    """Guard factory: `Depends(require_role('admin','recruiter'))`."""

    async def _guard(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in roles:
            raise AppError("forbidden", "Insufficient role", detail={"required": list(roles)})
        return user

    return _guard  # type: ignore


async def require_candidate(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.role != "candidate":
        raise AppError("forbidden", "Candidate role required")
    return user


async def service_auth(x_service_token: str | None = Header(default=None)) -> None:
    """Internal routes only (SPEC §12.4)."""
    verify_service_token(x_service_token)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
