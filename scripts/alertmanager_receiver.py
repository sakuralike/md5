from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

FORBIDDEN_KEY = re.compile(
    r"(?:authorization|cookie|password|secret|token|email|fingerprint|request_id|user_id)",
    re.IGNORECASE,
)
MAX_BODY_BYTES = 1_048_576
REDACTED = "[REDACTED]"


def sanitize(value: Any, key: str = "") -> Any:
    if key and FORBIDDEN_KEY.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def normalize_alertmanager_payload(payload: dict[str, Any]) -> dict[str, Any]:
    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        raise ValueError("Alertmanager payload must include at least one alert")
    normalized_alerts = []
    for alert in alerts:
        if not isinstance(alert, dict):
            raise TypeError("each Alertmanager alert must be an object")
        labels = alert.get("labels")
        if not isinstance(labels, dict) or not labels.get("alertname"):
            raise ValueError("each Alertmanager alert needs an alertname label")
        normalized_alerts.append(
            {
                "status": str(alert.get("status", "")),
                "labels": sanitize(labels),
                "annotations": sanitize(alert.get("annotations", {})),
                "starts_at": str(alert.get("startsAt", "")),
                "ends_at": str(alert.get("endsAt", "")),
                "fingerprint": sanitize(str(alert.get("fingerprint", "")), "fingerprint"),
            }
        )
    safe = {
        "received_at": datetime.now(UTC).isoformat(),
        "status": str(payload.get("status", "")),
        "receiver": str(payload.get("receiver", "")),
        "group_key": str(payload.get("groupKey", "")),
        "common_labels": sanitize(payload.get("commonLabels", {})),
        "common_annotations": sanitize(payload.get("commonAnnotations", {})),
        "alerts": normalized_alerts,
    }
    canonical = json.dumps(safe, ensure_ascii=False, sort_keys=True).encode("utf-8")
    safe["delivery_id"] = hashlib.sha256(canonical).hexdigest()[:24]
    return safe


class ReceiverState:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def append(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)


class AlertReceiverHandler(BaseHTTPRequestHandler):
    state = ReceiverState()

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json_response(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/events":
            events = self.state.snapshot()
            self._json_response(HTTPStatus.OK, {"count": len(events), "events": events})
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/alerts":
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("invalid request body size")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("request body must be an object")
            event = normalize_alertmanager_payload(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid_alert", "detail": str(exc)})
            return
        self.state.append(event)
        self._json_response(HTTPStatus.OK, {"status": "accepted", "delivery_id": event["delivery_id"]})

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic Alertmanager notification gateway for WP4 drills.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AlertReceiverHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
