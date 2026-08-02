from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveredNotification:
    kind: str
    recipient: str
    token: str


class NotificationGateway(Protocol):
    def send_account_token(self, *, kind: str, recipient: str, token: str) -> None: ...


class MemoryNotificationGateway:
    """仅供本地开发和自动化测试读取，不写入日志。"""

    def __init__(self) -> None:
        self.messages: list[DeliveredNotification] = []

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> None:
        self.messages.append(DeliveredNotification(kind=kind, recipient=recipient, token=token))

    def latest_token(self, *, kind: str, recipient: str) -> str:
        for message in reversed(self.messages):
            if message.kind == kind and message.recipient == recipient:
                return message.token
        raise LookupError(f"未找到 {kind} 通知")


class LoggingNotificationGateway:
    """邮件服务接入前的生产占位器；只记录不含令牌和邮箱的事件。"""

    def send_account_token(self, *, kind: str, recipient: str, token: str) -> None:
        logger.info(
            "account_notification_queued_without_provider",
            extra={"event": "account_notification_pending", "kind": kind},
        )
