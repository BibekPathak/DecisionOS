"""AgentGuard: the flagship DecisionOS demonstration.

AgentGuard shows how an AI agent's tool calls are authorized. The agent asks
DecisionOS whether it may use a tool; Jev (or the mock provider) returns a
probability distribution over ``allow`` / ``human_review`` / ``deny``; the
deterministic policy engine then determines what is actually permitted.

The model can never override the policy. The final action is what the calling
system is allowed to do.
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

EXAMPLE_NAME = "agent_guard"

# Tools the agent may attempt, and the fixture context file for each.
DEFAULT_TOOLS = (
    "read_file",
    "merge",
    "delete_database",
    "rotate_credentials",
)


@dataclass(frozen=True)
class AgentGuardReport:
    """The outcome of running the AgentGuard demo across several tools."""

    runs: list[ExampleRun]

    def render(self) -> str:
        blocks: list[str] = []
        for run in self.runs:
            blocks.append(f"=== AgentGuard: {run.name} ===")
            blocks.append("")
            blocks.append(format_run(run))
            blocks.append("")
        return "\n".join(blocks).rstrip() + "\n"


async def run_agent_guard(tool: str | None = None) -> AgentGuardReport:
    """Run the AgentGuard demo.

    Parameters
    ----------
    tool:
        The context file stem to run (e.g. ``"merge"``). When ``None`` every
        bundled tool context is run.
    """
    directory = example_directory(EXAMPLE_NAME)
    schema = load_schema(directory / "schema.json")
    evaluator = build_evaluator(schema)
    policy = load_policy_evaluator(directory, schema)

    contexts = load_contexts(directory)
    if tool is not None:
        if tool not in contexts:
            available = ", ".join(sorted(contexts))
            raise ValueError(f"unknown tool {tool!r}; available: {available}")
        contexts = {tool: contexts[tool]}

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
    return AgentGuardReport(runs=runs)


__all__ = ["DEFAULT_TOOLS", "EXAMPLE_NAME", "AgentGuardReport", "run_agent_guard"]
