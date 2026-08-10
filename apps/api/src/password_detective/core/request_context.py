from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
_REQUEST_ID: ContextVar[str] = ContextVar("password_detective_request_id", default="-")


def get_request_id() -> str:
    return _REQUEST_ID.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else f"req_{uuid.uuid4().hex}"
        )
        request.state.request_id = request_id
        token: Token[str] = _REQUEST_ID.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _REQUEST_ID.reset(token)
