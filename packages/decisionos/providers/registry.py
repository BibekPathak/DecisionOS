"""Provider registry.

Maps provider names to :class:`DecisionProvider` instances. The engine asks the
registry for a provider by name and never imports a concrete provider directly,
which keeps provider-specific behaviour out of the rest of DecisionOS.

The registry is populated with the always-available ``mock`` provider. The
``jev`` provider is registered lazily in Phase 7 (when Jev support lands) and
is only usable when an API key is configured. Any request for an unknown or
unavailable provider resolves to ``mock`` so the system keeps running without
external credentials.
"""

from __future__ import annotations

from collections.abc import Callable

from decisionos.config import Settings, get_settings
from decisionos.observability.logging import get_logger
from decisionos.providers.base import DecisionProvider
from decisionos.providers.mock import MockProvider

logger = get_logger(__name__)

ProviderFactory = Callable[[Settings], DecisionProvider]


class ProviderRegistry:
    """A registry of named provider factories.

    Factories take the resolved :class:`Settings` so providers can read their
    own configuration without global state.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._factories: dict[str, ProviderFactory] = {}
        self._instances: dict[str, DecisionProvider] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        """Register (or replace) a provider factory under ``name``."""
        self._factories[name] = factory
        self._instances.pop(name, None)

    def available(self) -> list[str]:
        """Return the names of registered providers."""
        return sorted(self._factories)

    def get(self, name: str | None) -> DecisionProvider:
        """Resolve a provider by name, falling back to ``mock``.

        An unknown name, or a provider whose factory raises, logs a warning and
        falls back to the mock provider rather than failing the request.
        """
        requested = name or self._settings.default_provider
        factory = self._factories.get(requested)
        if factory is None:
            if requested != "mock":
                logger.warning(
                    "provider.unknown_falling_back_to_mock",
                    requested=requested,
                    available=self.available(),
                )
            return self._mock()
        if requested in self._instances:
            return self._instances[requested]
        try:
            instance = factory(self._settings)
        except Exception as error:
            logger.warning(
                "provider.factory_failed_falling_back_to_mock",
                requested=requested,
                error=str(error),
            )
            return self._mock()
        self._instances[requested] = instance
        return instance

    def _mock(self) -> DecisionProvider:
        if "mock" not in self._instances:
            self._instances["mock"] = MockProvider()
        return self._instances["mock"]


_REGISTRY: ProviderRegistry | None = None


def get_registry(settings: Settings | None = None) -> ProviderRegistry:
    """Return the process-wide provider registry.

    Built-in providers (``mock`` now, ``jev`` from Phase 7) are registered the
    first time the registry is created. Provider factories import their
    concrete implementations lazily to avoid import cycles.
    """
    global _REGISTRY
    if _REGISTRY is None or settings is not None:
        registry = ProviderRegistry(settings)
        registry.register("mock", lambda _settings: MockProvider())
        from decisionos.providers.jev import build_jev_provider

        registry.register("jev", build_jev_provider)
        _REGISTRY = registry
    return _REGISTRY


def reset_registry() -> None:
    """Clear the process-wide registry (used by tests)."""
    global _REGISTRY
    _REGISTRY = None


__all__ = ["ProviderFactory", "ProviderRegistry", "get_registry", "reset_registry"]
