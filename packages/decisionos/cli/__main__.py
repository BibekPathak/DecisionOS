"""Allow ``python -m decisionos.cli`` to invoke the CLI."""

from __future__ import annotations

from decisionos.cli.main import app

if __name__ == "__main__":
    app()
