"""Common error envelope (SPEC §12). Every API error returns
`{"code", "message", "detail"}` with a stable machine `code`."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Machine codes enumerated in SPEC §12.
ERROR_CODES = {
    "invalid_transition",
    "link_invalid",
    "already_applied",
    "not_ready",
    "validation_error",
    "forbidden",
    "not_found",
    "conflict",
    "rate_limited",
    "unauthorized",
    "internal_error",
}

# Default HTTP status per code.
_CODE_STATUS = {
    "invalid_transition": 409,
    "link_invalid": 400,
    "already_applied": 409,
    "not_ready": 202,
    "validation_error": 422,
    "forbidden": 403,
    "not_found": 404,
    "conflict": 409,
    "rate_limited": 429,
    "unauthorized": 401,
    "internal_error": 500,
}


class AppError(Exception):
    """Raise anywhere in domain/API code to produce the standard envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        assert code in ERROR_CODES, f"unknown error code: {code}"
        self.code = code
        self.message = message
        self.status_code = status_code or _CODE_STATUS.get(code, 400)
        self.detail = detail or {}
        super().__init__(message)


def _envelope(code: str, message: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def install_exception_handlers(app) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "validation_error", "Request validation failed", {"errors": exc.errors()}
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Last-resort envelope so clients never see a bare 500 (SPEC §12).
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "Internal server error", {}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            429: "rate_limited",
        }.get(exc.status_code, "internal_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), {}),
        )
