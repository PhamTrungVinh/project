def test_health_is_live_and_returns_request_id(client):
    response = client.get("/health", headers={"X-Request-ID": "baseline-check"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "baseline-check"


def test_ready_checks_database(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["X-Request-ID"]


def test_version_and_metrics_are_available(client):
    version = client.get("/version")
    metrics = client.get("/metrics")

    assert version.status_code == 200
    assert version.json()["service"] == "fpt-customer-chatbot-api"
    assert "http_requests_total" in metrics.text
