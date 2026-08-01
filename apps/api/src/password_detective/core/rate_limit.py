from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from password_detective.core.errors import AppError


class InMemoryRateLimiter:
    """仅供单进程本地开发；集成环境由 Redis 实现替换。"""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        threshold = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])))
                raise AppError(
                    "rate_limit.exceeded",
                    "请求过于频繁，请稍后重试",
                    status_code=429,
                    details={"retry_after_seconds": retry_after},
                )
            events.append(now)


def rate_limit(scope: str, *, limit: int, window_seconds: int) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        request.app.state.rate_limiter.check(
            f"{scope}:{client_ip}", limit=limit, window_seconds=window_seconds
        )

    return dependency
