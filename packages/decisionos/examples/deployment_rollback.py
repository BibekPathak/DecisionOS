"""Deployment rollback simulator.

A second DecisionOS example: given observability signals about a recent
deployment, decide whether to ``continue``, ``rollback``, ``pause``, or
escalate to ``human_review``.

This is a *simulator*. DecisionOS returns a structured decision and this module
maps it to a plain description of what the calling system would do. It never
touches real infrastructure and executes no commands.
"""

from __future__ import annotations

from dataclasses import dataclass

from decisionos.examples.runner import (
    ExampleRun,
    build_evaluator,
    example_directory,
    format_run,
    load_contexts,
    load_policy_evaluator,
    load_schema,
    run_context,
)

EXAMPLE_NAME = "deployment_rollback"

# A plain-language description of what each action would mean to a deployment
# system. These are descriptions only; nothing is executed.
SIMULATED_ACTIONS: dict[str, str] = {
    "continue": "Deployment continues; no intervention.",
    "rollback": "Deployment would be reverted to the previous version.",
    "pause": "Deployment would be held while more signal is gathered.",
    "human_review": "A human would be paged before any automated action.",
}

DEFAULT_SCENARIOS = ("rolling_back", "healthy", "no_rollback_available")


@dataclass(frozen=True)
class RollbackReport:
    """The outcome of running the rollback simulator across scenarios."""

    runs: list[ExampleRun]

    def simulated_action(self, run: ExampleRun) -> str:
        return SIMULATED_ACTIONS.get(run.action, "No simulated action defined.")

    def render(self) -> str:
        blocks: list[str] = []
        for run in self.runs:
            blocks.append(f"=== Deployment rollback: {run.name} ===")
            blocks.append("")
            blocks.append(format_run(run))
            blocks.append(f"Simulated action: {self.simulated_action(run)}")
            blocks.append("")
        return "\n".join(blocks).rstrip() + "\n"


async def run_deployment_rollback(scenario: str | None = None) -> RollbackReport:
    """Run the deployment rollback simulator.

    Parameters
    ----------
    scenario:
        The context file stem to run (e.g. ``"rolling_back"``). When ``None``
        every bundled scenario is run.
    """
    directory = example_directory(EXAMPLE_NAME)
    schema = load_schema(directory / "schema.json")
    evaluator = build_evaluator(schema)
    policy = load_policy_evaluator(directory, schema)

    contexts = load_contexts(directory)
    if scenario is not None:
        if scenario not in contexts:
            available = ", ".join(sorted(contexts))
            raise ValueError(f"unknown scenario {scenario!r}; available: {available}")
        contexts = {scenario: contexts[scenario]}

    runs: list[ExampleRun] = []
    for name, context in contexts.items():
        runs.append(
            await run_context(
                name=name,
                context=context,
                schema=schema,
                evaluator=evaluator,
                policy=policy,
            )
        )
    return RollbackReport(runs=runs)


__all__ = [
    "DEFAULT_SCENARIOS",
    "EXAMPLE_NAME",
    "SIMULATED_ACTIONS",
    "RollbackReport",
    "run_deployment_rollback",
]
