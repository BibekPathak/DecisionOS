"""DecisionOS command line interface.

Only a health check is implemented in Phase 0; the remaining commands
(``evaluate``, ``decisions``, ``schemas``, ``policies``, ``calibration``)
are added in later phases.
"""

from __future__ import annotations

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
