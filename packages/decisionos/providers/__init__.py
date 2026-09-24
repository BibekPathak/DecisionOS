"""Decision providers.

The only place probabilistic intelligence enters DecisionOS. Providers return
:class:`~decisionos.models.RawDecision` output and never execute actions.
"""

from __future__ import annotations

from decisionos.providers.base import (
    DecisionProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from decisionos.providers.fixtures import FIXTURES, MockFixture
from decisionos.providers.jev import JevProvider, build_jev_provider
from decisionos.providers.mock import MockProvider
from decisionos.providers.registry import (
    ProviderFactory,
    ProviderRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    "FIXTURES",
    "DecisionProvider",
    "JevProvider",
    "MockFixture",
    "MockProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderFactory",
    "ProviderRateLimitError",
    "ProviderRegistry",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "build_jev_provider",
    "get_registry",
    "reset_registry",
]
