"""Tests for the DecisionOS CLI commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from decisionos.cli.main import app

runner = CliRunner()

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_health_command() -> None:
    result = runner.invoke(app, ["health"])
    assert result.exit_code == 0
    assert "decisionos" in result.stdout
    assert "default_provider" in result.stdout


def test_demo_agent_guard_merge() -> None:
    result = runner.invoke(app, ["demo", "agent_guard", "--case", "merge"])
    assert result.exit_code == 0
    assert "Decision: human_review" in result.stdout
    assert "Confidence: 91%" in result.stdout


def test_demo_agent_guard_all() -> None:
    result = runner.invoke(app, ["demo", "agent_guard"])
    assert result.exit_code == 0
    assert "=== AgentGuard:" in result.stdout


def test_demo_rollback() -> None:
    result = runner.invoke(app, ["demo", "deployment_rollback", "--case", "rolling_back"])
    assert result.exit_code == 0
    assert "Decision: rollback" in result.stdout
    assert "Simulated action:" in result.stdout


def test_demo_unknown_example() -> None:
    result = runner.invoke(app, ["demo", "nope"])
    assert result.exit_code != 0


def test_demo_unknown_case() -> None:
    result = runner.invoke(app, ["demo", "agent_guard", "--case", "nope"])
    assert result.exit_code != 0


def test_evaluate_acceptance_criteria_command() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--schema",
            "ToolAuthorization",
            "--context",
            str(EXAMPLES / "agent_guard" / "merge.json"),
        ],
    )
    assert result.exit_code == 0
    assert "Decision: human_review" in result.stdout
    assert "Confidence: 91%" in result.stdout
    assert "Risk: 87%" in result.stdout
    assert "human_review:  91.0%" in result.stdout
    assert "Provider: mock" in result.stdout


def test_evaluate_with_policy() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--schema",
            "ToolAuthorization",
            "--context",
            str(EXAMPLES / "agent_guard" / "merge.json"),
            "--policy",
            str(EXAMPLES / "agent_guard" / "policy.yaml"),
        ],
    )
    assert result.exit_code == 0
    assert "Policies:" in result.stdout
    assert "production-merge" in result.stdout


def test_evaluate_rollback_schema() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--schema",
            "DeploymentDecision",
            "--context",
            str(EXAMPLES / "deployment_rollback" / "rolling_back.json"),
        ],
    )
    assert result.exit_code == 0
    assert "Decision: rollback" in result.stdout


def test_evaluate_missing_context_errors() -> None:
    result = runner.invoke(
        app,
        ["evaluate", "--schema", "ToolAuthorization", "--context", "/nonexistent.json"],
    )
    assert result.exit_code != 0


def test_evaluate_unknown_schema_without_file_errors() -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--schema",
            "NotARealSchema",
            "--context",
            str(EXAMPLES / "agent_guard" / "merge.json"),
        ],
    )
    assert result.exit_code != 0
