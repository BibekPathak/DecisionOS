"""Unit tests for the request-context middleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware import RequestContextMiddleware
from decisionos.observability.context import get_request_context


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/echo")
    async def echo() -> dict[str, str | None]:
        context = get_request_context()
        return {"request_id": context.request_id}

    return TestClient(app)


def test_generates_request_id_when_absent() -> None:
    response = _client().get("/echo")
    assert response.status_code == 200
    assert response.json()["request_id"]
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_propagates_supplied_request_id() -> None:
    response = _client().get("/echo", headers={"X-Request-ID": "req_given"})
    assert response.json()["request_id"] == "req_given"
    assert response.headers["X-Request-ID"] == "req_given"


def test_request_context_is_reset_after_request() -> None:
    client = _client()
    client.get("/echo", headers={"X-Request-ID": "req_given"})
    # Outside a request there is no active context.
    assert get_request_context().request_id is None


def test_http_metrics_are_recorded() -> None:
    from decisionos.observability.metrics import render_metrics

    client = _client()
    client.get("/echo")
    text = render_metrics()
    assert "decisionos_http_request_latency_seconds_count" in text
    assert 'route="/echo"' in text
