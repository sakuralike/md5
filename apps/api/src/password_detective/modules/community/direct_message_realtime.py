from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from typing import Protocol

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class DirectWakePublishClient(Protocol):
    def publish(self, channel: str, message: str) -> int | None: ...

    def close(self) -> None: ...


class DirectWakePubSub(Protocol):
    async def subscribe(self, channel: str) -> object: ...

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> object | None: ...

    async def unsubscribe(self, channel: str) -> object: ...

    async def aclose(self) -> None: ...


class DirectWakeAsyncClient(Protocol):
    def pubsub(self) -> DirectWakePubSub: ...

    async def aclose(self) -> None: ...


def direct_stream_channel(user_id: str) -> str:
    return f"community:direct-stream:user:{user_id}"


def publish_direct_message_wakeups(
    redis_url: str,
    user_sequences: Mapping[str, int],
    *,
    client_factory: Callable[..., DirectWakePublishClient] | None = None,
) -> None:
    if not user_sequences:
        return
    client: DirectWakePublishClient | None = None
    try:
        factory = client_factory or Redis.from_url
        client = factory(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        for user_id, sequence in sorted(user_sequences.items()):
            payload = json.dumps(
                {"max_sequence": int(sequence)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            client.publish(direct_stream_channel(user_id), payload)
    except RedisError:
        logger.warning("Direct message Redis wakeup failed", exc_info=True)
    finally:
        if client is not None:
            try:
                client.close()
            except RedisError:
                logger.warning("Direct message Redis client close failed", exc_info=True)


class DirectStreamWakeSubscription:
    def __init__(
        self,
        *,
        user_id: str,
        pubsub: DirectWakePubSub,
        client: DirectWakeAsyncClient | None = None,
    ) -> None:
        self._user_id = user_id
        self._pubsub = pubsub
        self._client = client

    @classmethod
    async def connect(
        cls,
        redis_url: str,
        *,
        user_id: str,
        client_factory: Callable[..., DirectWakeAsyncClient] | None = None,
    ) -> DirectStreamWakeSubscription:
        factory = client_factory or AsyncRedis.from_url
        client = factory(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        pubsub = client.pubsub()
        await pubsub.subscribe(direct_stream_channel(user_id))
        return cls(user_id=user_id, pubsub=pubsub, client=client)

    async def wait(self, timeout_seconds: float) -> bool:
        try:
            message = await asyncio.wait_for(
                self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=timeout_seconds,
                ),
                timeout=max(0.1, timeout_seconds + 0.1),
            )
        except (TimeoutError, RedisError):
            return False
        return message is not None

    async def close(self) -> None:
        try:
            await self._pubsub.unsubscribe(direct_stream_channel(self._user_id))
        except RedisError:
            logger.warning("Direct message Redis unsubscribe failed", exc_info=True)
        try:
            await self._pubsub.aclose()
        except RedisError:
            logger.warning("Direct message Redis pubsub close failed", exc_info=True)
        if self._client is not None:
            try:
                await self._client.aclose()
            except RedisError:
                logger.warning("Direct message Redis async client close failed", exc_info=True)
