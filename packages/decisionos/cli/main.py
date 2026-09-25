"""DecisionOS command line interface.

Commands are added incrementally. Phase 10 provides the example runners
(``demo``), which build DecisionOS entirely in-process on the mock provider and
require no credentials, database, or network access.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from decisionos import __version__
from decisionos.config import get_settings

app = typer.Typer(
    name="decisionos",
    help="DecisionOS command line interface.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """DecisionOS command line interface.

    An explicit callback forces Typer to treat this as a command group, so
    subcommands are always addressed by name regardless of how many are
    registered.
    """


@app.command("health")
def health() -> None:
    """Print configuration status without contacting external services."""
    settings = get_settings()
    typer.echo(f"decisionos {__version__}")
    typer.echo(f"app_env:          {settings.app_env}")
    typer.echo(f"default_provider: {settings.default_provider}")
    typer.echo(f"jev_configured:   {settings.jev_configured}")
    typer.echo(f"database_url:     {_safe_db_url(settings.database_url)}")
    typer.echo(f"redis_url:        {settings.redis_url}")


@app.command("demo")
def demo(
    example: Annotated[
        str,
        typer.Argument(help="Example to run: 'agent_guard' or 'deployment_rollback'."),
    ] = "agent_guard",
    case: Annotated[
        str | None,
        typer.Option(
            "--case",
            "-c",
            help="A specific tool or scenario to run (e.g. 'merge', 'rolling_back').",
        ),
    ] = None,
) -> None:
    """Run a bundled DecisionOS example end to end on the mock provider."""
    from decisionos.examples import run_agent_guard, run_deployment_rollback
    from decisionos.observability.logging import configure_logging

    # Keep the demo output clean; the examples are illustrative, not a log sink.
    configure_logging("WARNING", json_logs=False)

    try:
        if example == "agent_guard":
            report = asyncio.run(run_agent_guard(case))
        elif example == "deployment_rollback":
            report = asyncio.run(run_deployment_rollback(case))
        else:
            raise typer.BadParameter(
                f"unknown example {example!r}; choose agent_guard or deployment_rollback"
            )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(report.render())


@app.command("evaluate")
def evaluate(
    schema: Annotated[str, typer.Option("--schema", help="Decision schema name.")],
    context: Annotated[
        Path, typer.Option("--context", help="Path to a JSON file holding the context.")
    ],
    schema_version: Annotated[int, typer.Option("--schema-version", help="Schema version.")] = 1,
    decision_type: Annotated[
        str | None,
        typer.Option("--decision-type", help="Decision type; defaults to the schema name."),
    ] = None,
    schema_file: Annotated[
        Path | None,
        typer.Option("--schema-file", help="Schema JSON file; auto-detected for bundled schemas."),
    ] = None,
    policy_file: Annotated[
        Path | None,
        typer.Option("--policy", help="Optional policy YAML file to apply."),
    ] = None,
    provider: Annotated[
        str, typer.Option("--provider", help="Provider name; defaults to 'mock'.")
    ] = "mock",
) -> None:
    """Evaluate a single context against a schema, in-process.

    Useful for local checks and CI. This does not persist anything and does not
    require a running API, database, or Jev credentials.
    """
    import json

    from decisionos.engine import DecisionEvaluator, InMemorySchemaResolver
    from decisionos.models import DecisionRequest
    from decisionos.observability.logging import configure_logging
    from decisionos.policies import PolicyEvaluator, load_policy_file
    from decisionos.providers import MockProvider
    from decisionos.providers.registry import ProviderRegistry

    configure_logging("WARNING", json_logs=False)

    if not context.is_file():
        raise typer.BadParameter(f"context file not found: {context}")
    context_data: dict[str, object] = json.loads(context.read_text(encoding="utf-8"))

    decision_schema = _resolve_schema(
        schema=schema,
        schema_version=schema_version,
        schema_file=schema_file,
        policy_file=policy_file,
    )
    registry = ProviderRegistry(get_settings())
    registry.register("mock", lambda _settings: MockProvider())
    evaluator = DecisionEvaluator(registry, InMemorySchemaResolver([decision_schema]))
    request = DecisionRequest(
        decision_type=decision_type or _snake_case(schema),
        schema_name=schema,
        schema_version=schema_version,
        context=context_data,
        provider=provider,
    )
    policy_evaluator = (
        PolicyEvaluator(load_policy_file(policy_file), decision_schema) if policy_file else None
    )

    async def _run():
        return await evaluator.evaluate(request, policy_evaluator=policy_evaluator)

    result = asyncio.run(_run())
    typer.echo(_format_result(result))


def _resolve_schema(
    *,
    schema: str,
    schema_version: int,
    schema_file: Path | None,
    policy_file: Path | None,
):
    """Resolve the schema to evaluate against.

    Preference order: an explicit ``--schema-file``; a bundled example schema
    whose name matches; otherwise a schema derived from a policy file's
    ``require`` targets.
    """
    import json

    from decisionos.models import DecisionSchema

    if schema_file is not None:
        if not schema_file.is_file():
            raise typer.BadParameter(f"schema file not found: {schema_file}")
        data = json.loads(schema_file.read_text(encoding="utf-8"))
        return DecisionSchema.model_validate(data)

    bundled = _find_bundled_schema(schema)
    if bundled is not None:
        return bundled

    actions = _actions_from_policy(policy_file) if policy_file else None
    if actions is None:
        raise typer.BadParameter(
            f"schema {schema!r} is not a bundled example and no --schema-file or "
            "--policy was supplied to determine its action set"
        )
    return DecisionSchema(name=schema, version=schema_version, actions=tuple(actions))


def _find_bundled_schema(name: str):
    """Return a bundled example schema by name, if one exists."""
    import json

    from decisionos.models import DecisionSchema

    examples_root = _examples_root()
    if examples_root is None:
        return None
    for schema_path in sorted(examples_root.glob("*/schema.json")):
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        if data.get("name") == name:
            return DecisionSchema.model_validate(data)
    return None


def _examples_root() -> Path | None:
    """Return the repository's data ``examples`` directory, if present.

    The Python package is also named ``examples`` (``decisionos.examples``), so
    a plain directory-name match is not enough. The data directory is the one
    that contains at least one ``*/schema.json``.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "examples"
        if candidate.is_dir() and any(candidate.glob("*/schema.json")):
            return candidate
    return None


def _actions_from_policy(policy_file: Path) -> list[str] | None:
    """Derive the action set from the ``require`` targets of a policy file."""
    from decisionos.policies import load_policy_file

    if not policy_file.is_file():
        raise typer.BadParameter(f"policy file not found: {policy_file}")
    policy = load_policy_file(policy_file)
    actions = list(dict.fromkeys(rule.action.require for rule in policy.rules))
    return actions or None


def _format_result(result) -> str:
    """Render an EvaluationResult using the shared example layout."""
    from decisionos.examples.runner import ExampleRun, format_run

    run = ExampleRun(
        name="evaluate",
        context={},
        result=result,
        policy_name="",
        policy_version=1,
    )
    return format_run(run)


def _snake_case(name: str) -> str:
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _safe_db_url(url: str) -> str:
    """Return a database URL with any password masked."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, host = rest.split("@", 1)
    if ":" in credentials:
        user = credentials.split(":", 1)[0]
        credentials = f"{user}:***"
    return f"{scheme}://{credentials}@{host}"


if __name__ == "__main__":
    app()
