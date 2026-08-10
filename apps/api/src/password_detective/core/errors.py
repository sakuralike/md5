from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_payload(request: Request, error: AppError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "details": error.details,
        "request_id": getattr(request.state, "request_id", None),
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers: dict[str, str] = {}
    retry_after = exc.details.get("retry_after_seconds")
    if exc.code == "rate_limit.exceeded" and isinstance(retry_after, int) and retry_after > 0:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(request, exc),
        headers=headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = [
        {
            "type": error.get("type"),
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg"),
        }
        for error in exc.errors()
    ]
    error = AppError(
        "request.validation_failed",
        "请求参数不符合要求",
        status_code=422,
        details={"errors": safe_errors},
    )
    return JSONResponse(status_code=422, content=error_payload(request, error))
