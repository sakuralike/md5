from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class HttpSecurityMiddleware:
    """Apply API response hardening and a bounded JSON request-body policy."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, max_json_body_bytes: int) -> None:
        self.app = app
        self.max_json_body_bytes = max_json_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").lower()
        guarded_receive = receive
        if _is_json_content_type(content_type):
            content_length = _parse_content_length(headers.get("content-length"))
            if content_length is not None and content_length > self.max_json_body_bytes:
                await self._send_too_large(scope, receive, send)
                return
            guarded_receive = await self._buffer_bounded_json_body(scope, receive, send)
            if guarded_receive is None:
                return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    if name not in response_headers:
                        response_headers[name] = value
                if "Cache-Control" not in response_headers:
                    response_headers["Cache-Control"] = "no-store"
                if response_headers.get("content-type", "").startswith("application/json"):
                    response_headers["Content-Security-Policy"] = (
                        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
                    )
            await send(message)

        await self.app(scope, guarded_receive, send_with_security_headers)

    async def _buffer_bounded_json_body(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> Receive | None:
        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            total += len(message.get("body", b""))
            if total > self.max_json_body_bytes:
                await self._send_too_large(scope, receive, send)
                return None
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        return replay_receive

    async def _send_too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        state = scope.get("state") or {}
        response = JSONResponse(
            status_code=413,
            content={
                "code": "request.body_too_large",
                "message": "JSON 请求体超过允许大小",
                "details": {"max_bytes": self.max_json_body_bytes},
                "request_id": state.get("request_id"),
            },
            headers={
                **_SECURITY_HEADERS,
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
                ),
            },
        )
        await response(scope, receive, send)


def _is_json_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip()
    return media_type == "application/json" or media_type.endswith("+json")


def _parse_content_length(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value >= 0 else None
