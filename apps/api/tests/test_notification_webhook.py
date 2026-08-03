from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from password_detective.core.config import Settings
from password_detective.core.notifications import WebhookNotificationGateway


class _SyntheticWebhookResponse:
    status = 202
    headers = {"X-Provider-Message-Id": "synthetic-message-1"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):  # noqa: ANN001
        del exc_type, exc, traceback
        return False


def test_webhook_gateway_signs_minimum_disclosure_payload_and_accepts_naive_due_at():
    captured = {}

    def opener(request, *, timeout):  # noqa: ANN001, ANN202
        captured["request"] = request
        captured["timeout"] = timeout
        return _SyntheticWebhookResponse()

    secret = "synthetic-webhook-secret-at-least-32-characters"
    gateway = WebhookNotificationGateway(
        url="https://notifications.synthetic.example.com/deliveries",
        secret=secret,
        timeout_seconds=7.5,
        opener=opener,
    )
    message_id = gateway.send_risk_alert(
        delivery_id="delivery-synthetic-1",
        kind="detected",
        recipient="operator@synthetic.example.com",
        alert_id="alert-synthetic-1",
        severity="high",
        due_at=datetime(2026, 8, 3, 12, 30),
    )

    assert message_id == "synthetic-message-1"
    assert captured["timeout"] == 7.5
    request = captured["request"]
    body = request.data
    payload = json.loads(body)
    assert payload == {
        "alert_id": "alert-synthetic-1",
        "delivery_id": "delivery-synthetic-1",
        "due_at": "2026-08-03T12:30:00+00:00",
        "kind": "detected",
        "recipient": "operator@synthetic.example.com",
        "severity": "high",
        "type": "risk_alert",
        "version": "notification-webhook-v1",
    }
    timestamp = request.headers["X-password-detective-timestamp"]
    expected = hmac.new(
        secret.encode(),
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    assert request.headers["X-password-detective-signature"] == f"sha256={expected}"
    assert "password" not in payload
    assert "token" not in payload


def test_webhook_notification_settings_require_https_and_strong_signing_secret():
    with pytest.raises(ValidationError):
        Settings(
            notification_backend="webhook",
            notification_webhook_url="http://notifications.synthetic.example.com",
            notification_webhook_secret="x" * 32,
        )
    with pytest.raises(ValidationError):
        Settings(
            notification_backend="webhook",
            notification_webhook_url="https://notifications.synthetic.example.com",
            notification_webhook_secret="too-short",
        )
