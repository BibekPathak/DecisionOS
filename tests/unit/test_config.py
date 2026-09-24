"""Phase 0 tests: configuration loading and environment-variable aliases."""

from __future__ import annotations

import pytest

from decisionos.config import Settings


def test_defaults_are_safe_without_env() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.default_provider == "mock"
    assert settings.jev_base_url == "https://api.typesafe.ai"
    assert settings.jev_model == "jev-latest"
    assert settings.jev_configured is False
    assert settings.auth_enabled is False


def test_jev_aliases_accept_typesafe_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts_example")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://example.test")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-1.13.0")
    settings = Settings(_env_file=None)
    assert settings.jev_api_key.get_secret_value() == "ts_example"
    assert settings.jev_base_url == "https://example.test"
    assert settings.jev_model == "jev-1.13.0"
    assert settings.jev_configured is True


def test_jev_native_names_win_when_both_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_KEY", "native")
    monkeypatch.setenv("TYPESAFE_API_KEY", "upstream")
    settings = Settings(_env_file=None)
    assert settings.jev_api_key.get_secret_value() == "native"


def test_secret_is_not_exposed_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_KEY", "super-secret-value")
    settings = Settings(_env_file=None)
    assert "super-secret-value" not in repr(settings)


def test_auth_enabled_is_false_in_development_and_test() -> None:
    assert Settings(_env_file=None, app_env="development").auth_enabled is False
    assert Settings(_env_file=None, app_env="test").auth_enabled is False


def test_is_production_flag() -> None:
    assert Settings(_env_file=None, app_env="production").is_production is True
    assert Settings(_env_file=None, app_env="development").is_production is False
