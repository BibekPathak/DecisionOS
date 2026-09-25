"""Tests for the bundled AgentGuard and deployment rollback examples."""

from __future__ import annotations

import pytest

from decisionos.examples import (
    format_run,
    run_agent_guard,
    run_deployment_rollback,
)
from decisionos.examples.runner import example_directory, load_contexts, load_schema


@pytest.mark.asyncio
async def test_agent_guard_merge_matches_spec() -> None:
    report = await run_agent_guard("merge")
    assert len(report.runs) == 1
    run = report.runs[0]
    assert run.action == "human_review"
    assert run.model_action == "human_review"
    assert run.decision.confidence == pytest.approx(0.91)
    assert run.decision.risk == pytest.approx(0.87)
    assert run.decision.probabilities == {
        "allow": 0.08,
        "human_review": 0.91,
        "deny": 0.01,
    }
    assert run.triggered_rules == ["production-merge"]
    assert run.decision.provider == "mock"


@pytest.mark.asyncio
async def test_agent_guard_delete_database_is_denied() -> None:
    report = await run_agent_guard("delete_database")
    assert report.runs[0].action == "deny"
    assert "dangerous-database-operation" in report.runs[0].triggered_rules


@pytest.mark.asyncio
async def test_agent_guard_read_file_is_allowed() -> None:
    report = await run_agent_guard("read_file")
    assert report.runs[0].action == "allow"


@pytest.mark.asyncio
async def test_agent_guard_rotate_credentials_requires_review() -> None:
    report = await run_agent_guard("rotate_credentials")
    assert report.runs[0].action == "human_review"


@pytest.mark.asyncio
async def test_agent_guard_runs_every_tool_by_default() -> None:
    report = await run_agent_guard()
    assert len(report.runs) >= 4
    assert report.render().startswith("=== AgentGuard:")


@pytest.mark.asyncio
async def test_agent_guard_unknown_tool_raises() -> None:
    with pytest.raises(ValueError, match="unknown tool"):
        await run_agent_guard("does_not_exist")


@pytest.mark.asyncio
async def test_policy_endorses_model_action() -> None:
    # The AgentGuard merge context: the model already says human_review and the
    # policy agrees, so it is not flagged as an override.
    report = await run_agent_guard("merge")
    run = report.runs[0]
    assert run.overridden is False
    assert "production-merge" in run.triggered_rules


@pytest.mark.asyncio
async def test_rollback_triggered_scenario() -> None:
    report = await run_deployment_rollback("rolling_back")
    run = report.runs[0]
    assert run.action == "rollback"
    assert run.decision.probabilities["rollback"] == pytest.approx(0.91)
    assert run.decision.probabilities["continue"] == pytest.approx(0.03)
    assert set(run.triggered_rules) >= {"severe-error-rate", "latency-regression"}


@pytest.mark.asyncio
async def test_rollback_healthy_scenario() -> None:
    report = await run_deployment_rollback("healthy")
    assert report.runs[0].action == "continue"


@pytest.mark.asyncio
async def test_rollback_unavailable_scenario_escalates() -> None:
    report = await run_deployment_rollback("no_rollback_available")
    assert report.runs[0].action == "human_review"


@pytest.mark.asyncio
async def test_rollback_runs_all_scenarios_by_default() -> None:
    report = await run_deployment_rollback()
    assert len(report.runs) == 3
    # The simulator maps every action to a description and executes nothing.
    for run in report.runs:
        assert report.simulated_action(run)


@pytest.mark.asyncio
async def test_rollback_unknown_scenario_raises() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        await run_deployment_rollback("nope")


@pytest.mark.asyncio
async def test_render_contains_expected_sections() -> None:
    report = await run_agent_guard("merge")
    text = report.render()
    assert "Decision: human_review" in text
    assert "Confidence: 91%" in text
    assert "Risk: 87%" in text
    assert "Probabilities:" in text
    assert "Provider: mock" in text
    assert "production-merge \u2713" in text


def test_format_run_is_reusable() -> None:
    assert callable(format_run)


def test_example_directory_resolves() -> None:
    agent_guard = example_directory("agent_guard")
    assert (agent_guard / "schema.json").is_file()
    assert (agent_guard / "policy.yaml").is_file()


def test_load_schema_and_contexts() -> None:
    directory = example_directory("agent_guard")
    schema = load_schema(directory / "schema.json")
    assert schema.name == "ToolAuthorization"
    assert set(schema.actions) == {"allow", "human_review", "deny"}
    contexts = load_contexts(directory)
    assert "merge" in contexts
    assert "schema" not in contexts
