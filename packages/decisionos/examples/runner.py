"""Reusable machinery for the bundled DecisionOS examples.

Examples are plain directories containing a ``schema.json``, a ``policy.yaml``,
and one or more context ``*.json`` files. This module loads them, runs them
through the real engine with the mock provider, and formats a human-readable
report.

The examples never require credentials, a database, or the network: they use
the in-memory schema resolver and the MockProvider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decisionos.config import Settings
from decisionos.engine import DecisionEvaluator, EvaluationResult, InMemorySchemaResolver
from decisionos.models import Decision, DecisionSchema
from decisionos.policies import PolicyEvaluator, load_policy_file
from decisionos.providers import MockProvider
from decisionos.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class ExampleRun:
    """The result of running one example context through DecisionOS."""

    name: str
    context: dict[str, Any]
    result: EvaluationResult
    policy_name: str
    policy_version: int

    @property
    def action(self) -> str:
        return self.result.decision.action

    @property
    def model_action(self) -> str:
        if self.result.model_decision is not None:
            return self.result.model_decision.action
        return self.result.decision.action

    @property
    def overridden(self) -> bool:
        return self.result.overridden

    @property
    def triggered_rules(self) -> list[str]:
        return list(self.result.triggered_rules)

    @property
    def decision(self) -> Decision:
        return self.result.decision


def example_directory(name: str) -> Path:
    """Return the path to a bundled example directory.

    Examples live at the repository root under ``examples/``. This resolves
    relative to the repository, so it works from a source checkout and from the
    Docker image (where the package and examples share a parent).
    """
    here = Path(__file__).resolve()
    # packages/decisionos/examples/runner.py -> repository root
    for parent in here.parents:
        candidate = parent / "examples" / name
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"example {name!r} not found")


def load_schema(path: Path) -> DecisionSchema:
    """Load a ``DecisionSchema`` from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return DecisionSchema.model_validate(data)


def load_contexts(directory: Path, *, exclude: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Load every ``*.json`` context file in ``directory`` (except schema.json)."""
    exclude = exclude or set()
    contexts: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.name in exclude or path.name == "schema.json":
            continue
        contexts[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return contexts


def build_evaluator(schema: DecisionSchema) -> DecisionEvaluator:
    """Build an evaluator over the mock provider and an in-memory schema."""
    registry = ProviderRegistry(Settings(_env_file=None))
    registry.register("mock", lambda _settings: MockProvider())
    return DecisionEvaluator(registry, InMemorySchemaResolver([schema]))


async def run_context(
    *,
    name: str,
    context: dict[str, Any],
    schema: DecisionSchema,
    evaluator: DecisionEvaluator,
    policy: PolicyEvaluator,
) -> ExampleRun:
    """Evaluate one context and return an :class:`ExampleRun`."""
    from decisionos.models import DecisionRequest

    request = DecisionRequest(
        decision_type=_decision_type(schema.name),
        schema_name=schema.name,
        schema_version=schema.version,
        context=context,
        provider="mock",
    )
    result = await evaluator.evaluate(request, policy_evaluator=policy)
    return ExampleRun(
        name=name,
        context=context,
        result=result,
        policy_name=policy.policy.name,
        policy_version=policy.policy.version,
    )


def load_policy_evaluator(directory: Path, schema: DecisionSchema) -> PolicyEvaluator:
    """Load ``policy.yaml`` from ``directory`` bound to ``schema``."""
    policy = load_policy_file(directory / "policy.yaml")
    return PolicyEvaluator(policy, schema)


def _decision_type(schema_name: str) -> str:
    """Derive a snake_case decision type from a schema name."""
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", schema_name).lower()


def format_run(run: ExampleRun) -> str:
    """Format an example run in the project's acceptance-criteria layout."""
    decision = run.decision
    lines: list[str] = []
    lines.append(f"Decision: {decision.action}")
    lines.append(f"Confidence: {decision.confidence:.0%}")
    if decision.risk is not None:
        lines.append(f"Risk: {decision.risk:.0%}")
    lines.append("")
    lines.append("Probabilities:")
    width = max((len(action) for action in decision.probabilities), default=0)
    for action, probability in sorted(decision.probabilities.items()):
        lines.append(f"  {action.ljust(width)}: {probability:>6.1%}")
    lines.append("")
    if run.triggered_rules:
        lines.append("Policies:")
        for rule in run.triggered_rules:
            lines.append(f"  {rule} \u2713")
        lines.append("")
    lines.append(f"Provider: {decision.provider}")
    lines.append(f"Latency: {decision.latency_ms:.0f}ms")
    return "\n".join(lines)


__all__ = [
    "ExampleRun",
    "build_evaluator",
    "example_directory",
    "format_run",
    "load_contexts",
    "load_policy_evaluator",
    "load_schema",
    "run_context",
]
