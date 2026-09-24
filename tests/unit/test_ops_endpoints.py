"""Phase 0 tests: API skeleton boots and exposes operational endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from decisionos.config import Settings


@pytest.fixture()
def client() -> TestClient:
    settings = Settings(_env_file=None, app_env="test")
    return TestClient(create_app(settings))


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_metrics_is_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "decisionos_decisions_total" in response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_openapi_documents_ops_endpoints(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "DecisionOS"
    assert "/health" in spec["paths"]
    assert "/ready" in spec["paths"]
    assert "/metrics" in spec["paths"]
