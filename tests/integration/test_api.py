"""Integration tests for the HTTP API.

Each test exercises the real stack: FastAPI -> engine -> mock provider ->
policy engine -> PostgreSQL.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

TOOL_SCHEMA = {
    "name": "ToolAuthorization",
    "version": 1,
    "actions": ["allow", "human_review", "deny"],
}

POLICY = {
    "name": "production-agent-policy",
    "version": 1,
    "rules": [
        {
            "name": "production-merge",
            "when": {"environment": "production", "tool": "github.merge"},
            "action": {"require": "human_review"},
        },
        {
            "name": "high-risk",
            "when": {"risk": {"gt": 0.9}},
            "action": {"require": "deny"},
        },
    ],
}

DECISION_BODY = {
    "decision_type": "tool_authorization",
    "schema_name": "ToolAuthorization",
    "schema_version": 1,
    "context": {
        "agent": "deploy-agent",
        "tool": "github.merge",
        "repository": "org/project",
        "environment": "production",
        "tests_passed": False,
    },
}


async def _register_schema(client) -> None:
    response = await client.post("/v1/schemas", json=TOOL_SCHEMA)
    assert response.status_code == 201


async def _register_policy(client) -> None:
    response = await client.post("/v1/policies", json=POLICY)
    assert response.status_code == 201


async def test_health_and_ready(api_client) -> None:
    assert (await api_client.get("/health")).json()["status"] == "ok"
    assert (await api_client.get("/ready")).json()["status"] == "ready"


async def test_metrics_exposes_prometheus_text(api_client) -> None:
    response = await api_client.get("/metrics")
    assert response.status_code == 200
    assert "decisionos_decisions_total" in response.text


async def test_create_decision_end_to_end(api_client) -> None:
    await _register_schema(api_client)
    await _register_policy(api_client)
    response = await api_client.post(
        "/v1/decisions", json={**DECISION_BODY, "policy": "production-agent-policy@1"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["action"] == "human_review"
    assert body["confidence"] == pytest.approx(0.91)
    assert body["risk"] == pytest.approx(0.87)
    assert body["provider"] == "mock"
    assert body["policy"]["triggered_rules"] == ["production-merge"]
    assert body["policy"]["overridden"] is False


async def test_decisions_are_persisted_and_retrievable(api_client) -> None:
    await _register_schema(api_client)
    created = (await api_client.post("/v1/decisions", json=DECISION_BODY)).json()
    fetched = await api_client.get(f"/v1/decisions/{created['decision_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["decision_id"] == created["decision_id"]
    assert fetched.json()["action"] == created["action"]


async def test_get_missing_decision_returns_404(api_client) -> None:
    assert (await api_client.get("/v1/decisions/nope")).status_code == 404


async def test_missing_schema_returns_404(api_client) -> None:
    response = await api_client.post(
        "/v1/decisions", json={**DECISION_BODY, "schema_name": "Missing"}
    )
    assert response.status_code == 404


async def test_unknown_policy_returns_422(api_client) -> None:
    await _register_schema(api_client)
    response = await api_client.post(
        "/v1/decisions", json={**DECISION_BODY, "policy": "does-not-exist"}
    )
    assert response.status_code == 422


async def test_idempotency_key_prevents_duplicate_decisions(api_client) -> None:
    await _register_schema(api_client)
    headers = {"Idempotency-Key": "idem-123"}
    first = await api_client.post("/v1/decisions", json=DECISION_BODY, headers=headers)
    second = await api_client.post("/v1/decisions", json=DECISION_BODY, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["decision_id"] == second.json()["decision_id"]
    listing = (await api_client.get("/v1/decisions")).json()
    assert len(listing) == 1


async def test_explanation_reports_structured_evidence(api_client) -> None:
    await _register_schema(api_client)
    await _register_policy(api_client)
    created = (
        await api_client.post(
            "/v1/decisions", json={**DECISION_BODY, "policy": "production-agent-policy@1"}
        )
    ).json()
    response = await api_client.get(f"/v1/decisions/{created['decision_id']}/explanation")
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "human_review"
    assert body["policy_rules_triggered"] == ["production-merge"]
    assert body["policy_precedence"] == "required_human_review"
    assert body["provider"] == "mock"
    assert len(body["lifecycle"]) >= 5
    assert body["model_probabilities"]["human_review"] == pytest.approx(0.91)


async def test_explanation_missing_decision_returns_404(api_client) -> None:
    assert (await api_client.get("/v1/decisions/nope/explanation")).status_code == 404


async def test_record_outcome(api_client) -> None:
    await _register_schema(api_client)
    created = (await api_client.post("/v1/decisions", json=DECISION_BODY)).json()
    response = await api_client.post(
        f"/v1/decisions/{created['decision_id']}/outcome",
        json={"actual_outcome": "safe", "success": True},
    )
    assert response.status_code == 201
    assert response.json()["actual_outcome"] == "safe"
    assert response.json()["success"] is True


async def test_record_outcome_missing_decision_returns_404(api_client) -> None:
    response = await api_client.post(
        "/v1/decisions/nope/outcome",
        json={"actual_outcome": "safe", "success": True},
    )
    assert response.status_code == 404


async def test_list_decisions_with_filters(api_client) -> None:
    await _register_schema(api_client)
    await api_client.post("/v1/decisions", json=DECISION_BODY)
    await api_client.post(
        "/v1/decisions",
        json={**DECISION_BODY, "context": {"tool": "read_file"}},
    )
    all_decisions = (await api_client.get("/v1/decisions")).json()
    assert len(all_decisions) == 2
    filtered = (await api_client.get("/v1/decisions", params={"action": "allow"})).json()
    assert len(filtered) == 1


async def test_schema_registration_is_idempotent(api_client) -> None:
    assert (await api_client.post("/v1/schemas", json=TOOL_SCHEMA)).status_code == 201
    assert (await api_client.post("/v1/schemas", json=TOOL_SCHEMA)).status_code == 201
    listing = (await api_client.get("/v1/schemas")).json()
    assert len(listing) == 1


async def test_schema_conflict_returns_409(api_client) -> None:
    await _register_schema(api_client)
    conflicting = {**TOOL_SCHEMA, "actions": ["allow", "deny"]}
    assert (await api_client.post("/v1/schemas", json=conflicting)).status_code == 409


async def test_get_and_list_schemas(api_client) -> None:
    await _register_schema(api_client)
    fetched = await api_client.get("/v1/schemas/ToolAuthorization/1")
    assert fetched.status_code == 200
    assert fetched.json()["actions"] == ["allow", "human_review", "deny"]
    assert (await api_client.get("/v1/schemas/ToolAuthorization/9")).status_code == 404


async def test_policy_invalid_returns_422(api_client) -> None:
    response = await api_client.post(
        "/v1/policies",
        json={
            "name": "bad",
            "version": 1,
            "rules": [
                {"name": "r", "when": {"x": {"between": [1, 2]}}, "action": {"require": "deny"}}
            ],
        },
    )
    assert response.status_code == 422


async def test_get_and_list_policies(api_client) -> None:
    await _register_policy(api_client)
    fetched = await api_client.get("/v1/policies/production-agent-policy")
    assert fetched.status_code == 200
    assert fetched.json()["version"] == 1
    by_version = await api_client.get("/v1/policies/production-agent-policy@1")
    assert by_version.status_code == 200
    assert len((await api_client.get("/v1/policies")).json()) == 1
    assert (await api_client.get("/v1/policies/missing")).status_code == 404


async def test_calibration_returns_honest_empty_report(api_client) -> None:
    response = await api_client.get("/v1/calibration")
    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 0
    assert body["brier_score"] is None
    assert body["expected_calibration_error"] is None
    assert body["buckets"] == []


async def _create_decision_with_outcome(api_client, *, context: dict, success: bool) -> str:
    created = (
        await api_client.post("/v1/decisions", json={**DECISION_BODY, "context": context})
    ).json()
    decision_id = created["decision_id"]
    response = await api_client.post(
        f"/v1/decisions/{decision_id}/outcome",
        json={"actual_outcome": "safe" if success else "unsafe", "success": success},
    )
    assert response.status_code == 201
    return decision_id


async def test_calibration_uses_recorded_outcomes(api_client) -> None:
    await _register_schema(api_client)
    context = {
        "agent": "deploy-agent",
        "tool": "github.merge",
        "repository": "production-repo",
        "tests_passed": False,
    }
    await _create_decision_with_outcome(api_client, context=context, success=True)
    await _create_decision_with_outcome(api_client, context=context, success=False)
    response = await api_client.get("/v1/calibration")
    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 2
    assert body["brier_score"] is not None
    assert body["expected_calibration_error"] is not None
    assert sum(bucket["count"] for bucket in body["buckets"]) == 2


async def test_calibration_ignores_decisions_without_outcomes(api_client) -> None:
    await _register_schema(api_client)
    await api_client.post("/v1/decisions", json=DECISION_BODY)
    body = (await api_client.get("/v1/calibration")).json()
    assert body["sample_count"] == 0


async def test_calibration_filters_by_provider(api_client) -> None:
    await _register_schema(api_client)
    await _create_decision_with_outcome(api_client, context={"tool": "read_file"}, success=True)
    matching = (await api_client.get("/v1/calibration", params={"provider": "mock"})).json()
    assert matching["sample_count"] == 1
    non_matching = (await api_client.get("/v1/calibration", params={"provider": "jev"})).json()
    assert non_matching["sample_count"] == 0


async def test_calibration_filters_by_decision_type(api_client) -> None:
    await _register_schema(api_client)
    await _create_decision_with_outcome(api_client, context={"tool": "read_file"}, success=True)
    matching = (
        await api_client.get("/v1/calibration", params={"decision_type": "tool_authorization"})
    ).json()
    assert matching["sample_count"] == 1
    non_matching = (
        await api_client.get("/v1/calibration", params={"decision_type": "other"})
    ).json()
    assert non_matching["sample_count"] == 0


async def test_calibration_filters_by_action(api_client) -> None:
    await _register_schema(api_client)
    await _create_decision_with_outcome(api_client, context={"tool": "read_file"}, success=True)
    matching = (await api_client.get("/v1/calibration", params={"action": "allow"})).json()
    assert matching["sample_count"] == 1
    non_matching = (await api_client.get("/v1/calibration", params={"action": "deny"})).json()
    assert non_matching["sample_count"] == 0


async def test_calibration_sets_metric_gauge(api_client) -> None:
    from decisionos.observability.metrics import render_metrics

    await _register_schema(api_client)
    await _create_decision_with_outcome(api_client, context={"tool": "read_file"}, success=True)
    assert (await api_client.get("/v1/calibration")).status_code == 200
    assert "decisionos_calibration_error" in render_metrics()


async def test_context_size_limit_enforced(api_client) -> None:
    await _register_schema(api_client)
    big = {**DECISION_BODY, "context": {"blob": "x" * (70 * 1024)}}
    response = await api_client.post("/v1/decisions", json=big)
    assert response.status_code in {413, 422}


async def test_rate_limit_returns_429(api_client) -> None:
    from decisionos.storage import RateLimiter

    api_client  # noqa: B018 - fixture establishes app state
    # Tighten the limiter, then exceed it.
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.state.rate_limiter = RateLimiter(app.state.redis_backend, limit=2)
    await _register_schema(api_client)
    await api_client.post("/v1/decisions", json=DECISION_BODY)
    await api_client.post("/v1/decisions", json=DECISION_BODY)
    third = await api_client.post("/v1/decisions", json=DECISION_BODY)
    assert third.status_code == 429
    assert "Retry-After" in third.headers


async def test_invalid_request_body_returns_422(api_client) -> None:
    response = await api_client.post("/v1/decisions", json={"decision_type": "x"})
    assert response.status_code == 422
