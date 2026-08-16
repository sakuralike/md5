from fastapi.testclient import TestClient


def test_notification_stream_cors_preflight_allows_replay_cursor(client: TestClient) -> None:
    response = client.options(
        "/api/v1/community/notifications/stream",
        headers={
            "Origin": "http://testserver",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,last-event-id",
        },
    )

    assert response.status_code == 200
    allowed_headers = {
        item.strip().lower()
        for item in response.headers["Access-Control-Allow-Headers"].split(",")
    }
    assert "authorization" in allowed_headers
    assert "last-event-id" in allowed_headers
