def test_liveness_and_readiness(client):
    live = client.get("/api/v1/health/live")
    ready = client.get("/api/v1/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"
    assert live.headers["X-Request-ID"].startswith("req_")


def test_valid_request_id_is_echoed(client):
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "test-request-12345"})
    assert response.headers["X-Request-ID"] == "test-request-12345"
