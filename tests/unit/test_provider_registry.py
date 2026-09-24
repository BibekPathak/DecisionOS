"""Unit tests for ProviderRegistry resolution and fallback."""

from __future__ import annotations

import pytest

from decisionos.config import Settings
from decisionos.providers import (
    MockProvider,
    ProviderRegistry,
    get_registry,
    reset_registry,
)
from decisionos.providers.base import ProviderUnavailableError


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_registry()
    yield
    reset_registry()


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_default_provider_is_mock() -> None:
    registry = get_registry(_settings())
    assert registry.get(None).name == "mock"


def test_mock_is_always_available() -> None:
    registry = get_registry(_settings())
    assert "mock" in registry.available()
    assert isinstance(registry.get("mock"), MockProvider)


def test_unknown_provider_falls_back_to_mock() -> None:
    registry = get_registry(_settings())
    assert registry.get("no-such-provider").name == "mock"


def test_jev_without_key_falls_back_to_mock() -> None:
    registry = get_registry(_settings(jev_api_key=""))
    assert registry.get("jev").name == "mock"


def test_registry_instances_are_reused() -> None:
    registry = get_registry(_settings())
    assert registry.get("mock") is registry.get("mock")


def test_register_replaces_factory() -> None:
    registry = ProviderRegistry(_settings())
    registry.register("mock", lambda _settings: MockProvider(latency_ms=1.0))
    assert isinstance(registry.get("mock"), MockProvider)


def test_failing_factory_falls_back_to_mock() -> None:
    registry = ProviderRegistry(_settings())

    def broken(_settings: Settings) -> MockProvider:
        raise ProviderUnavailableError("nope", provider="broken")

    registry.register("broken", broken)
    assert registry.get("broken").name == "mock"


def test_default_provider_setting_is_honoured() -> None:
    registry = get_registry(_settings(default_provider="mock"))
    assert registry.get(None).name == "mock"


def test_custom_registry_is_independent_of_global() -> None:
    custom = ProviderRegistry(_settings())
    custom.register("mock", lambda _settings: MockProvider(latency_ms=99.0))
    assert custom.get("mock") is not get_registry(_settings()).get("mock")
