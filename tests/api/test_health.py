from app.api import health


def test_health_reports_process_liveness(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_missing_dependencies(client, monkeypatch):
    monkeypatch.setattr(health, "_redis_ready", lambda: False)
    monkeypatch.setattr(health, "_workers_ready", lambda: False)

    response = client.get("/api/ready")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "not_ready"
    assert detail["checks"]["redis"] is False
    assert detail["checks"]["workers"] is False
    assert detail["checks"]["reference_index"] is False
