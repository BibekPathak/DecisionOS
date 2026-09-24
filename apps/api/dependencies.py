"""FastAPI dependencies.

Phase 0 exposes the settings dependency. Authentication, idempotency, and
rate-limit dependencies are added in Phase 6.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from decisionos.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

__all__ = ["SettingsDep"]
