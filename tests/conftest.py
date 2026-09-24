"""Shared pytest fixtures and import-path setup for DecisionOS tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for relative in ("packages", "apps"):
    path = str(REPO_ROOT / relative)
    if path not in sys.path:
        sys.path.insert(0, path)
