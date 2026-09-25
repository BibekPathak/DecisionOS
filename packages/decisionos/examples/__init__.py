"""Bundled, runnable DecisionOS examples.

Each example is a self-contained demonstration that runs on the mock provider
and requires no credentials, database, or network access:

* :mod:`decisionos.examples.agent_guard` — authorize AI agent tool calls.
* :mod:`decisionos.examples.deployment_rollback` — simulate a rollback decision.

The examples are also the source of truth for the repository's ``examples/``
directories: schemas, policies, and context fixtures live there and are loaded
by :mod:`decisionos.examples.runner`.
"""

from __future__ import annotations

from decisionos.examples.agent_guard import AgentGuardReport, run_agent_guard
from decisionos.examples.deployment_rollback import (
    RollbackReport,
    run_deployment_rollback,
)
from decisionos.examples.runner import ExampleRun, format_run

__all__ = [
    "AgentGuardReport",
    "ExampleRun",
    "RollbackReport",
    "format_run",
    "run_agent_guard",
    "run_deployment_rollback",
]
