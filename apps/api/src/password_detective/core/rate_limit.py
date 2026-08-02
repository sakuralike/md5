from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Protocol

from fastapi import Request
from redis import Redis
from redis.exceptions import RedisError

from password_detective.core.errors import AppError


class RateLimiter(Protocol):
    def check(self, key: str, *, limit: int, window_seconds: int) -> None: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


class InMemoryRateLimiter:
    """单进程开发后端；生产与集成环境必须显式选择 Redis。"""

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
                raise _rate_limit_error(retry_after)
            events.append(now)

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


class RedisRateLimiter:
    """基于 Redis 固定时间窗的多实例共享限流器。"""

    def __init__(self, client: Redis, *, namespace: str) -> None:
        self._client = client
        self._namespace = namespace.strip(":")

    @classmethod
    def from_url(cls, url: str, *, namespace: str) -> RedisRateLimiter:
        return cls(Redis.from_url(url, decode_responses=True), namespace=namespace)

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = int(time.time())
        bucket = now // window_seconds
        redis_key = f"{self._namespace}:rate-limit:{key}:{bucket}"
        try:
            pipeline = self._client.pipeline(transaction=True)
            pipeline.incr(redis_key)
            pipeline.expire(redis_key, window_seconds + 1, nx=True)
            count, _ = pipeline.execute()
        except RedisError as exc:
            raise AppError(
                "rate_limit.backend_unavailable",
                "请求保护服务暂时不可用，请稍后重试",
                status_code=503,
            ) from exc
        if int(count) > limit:
            retry_after = max(1, window_seconds - (now % window_seconds))
            raise _rate_limit_error(retry_after)

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except RedisError:
            return False

    def close(self) -> None:
        self._client.close()


def _rate_limit_error(retry_after: int) -> AppError:
    return AppError(
        "rate_limit.exceeded",
        "请求过于频繁，请稍后重试",
        status_code=429,
        details={"retry_after_seconds": retry_after},
    )


def rate_limit(scope: str, *, limit: int, window_seconds: int) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        request.app.state.rate_limiter.check(
            f"{scope}:{client_ip}", limit=limit, window_seconds=window_seconds
        )

    return dependency
