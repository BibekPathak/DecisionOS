"""Application configuration for DecisionOS.

Configuration is loaded from environment variables (and an optional ``.env``
file) via ``pydantic-settings``. Secrets are never logged; the ``Settings``
object is intentionally explicit about which fields are secret.

Jev configuration accepts both the DecisionOS-native ``JEV_*`` names and the
upstream TypeSafe SDK ``TYPESAFE_*`` names, so a developer who already has a
TypeSafe environment can run DecisionOS without renaming anything.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "production"]

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://decisionos:decisionos@localhost:5432/decisionos"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class Settings(BaseSettings):
    """Runtime configuration.

    Every field can be provided via an environment variable of the same name
    (case-insensitive) or through a ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_env: AppEnv = "development"
    app_name: str = "decisionos"
    log_level: str = "INFO"
    debug: bool = False

    # --- API -------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # API key required by clients calling the DecisionOS API. In development an
    # empty value disables authentication so local demos run without setup.
    api_key: SecretStr = SecretStr("")
    # Maximum serialized size (bytes) accepted for a decision ``context``.
    max_context_bytes: int = 64 * 1024

    # --- Database --------------------------------------------------------
    database_url: str = _DEFAULT_DATABASE_URL
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # --- Redis -----------------------------------------------------------
    redis_url: str = _DEFAULT_REDIS_URL
    idempotency_ttl_seconds: int = 60 * 60 * 24
    rate_limit_per_minute: int = 600

    # --- Provider selection ---------------------------------------------
    # The default provider used when a decision request does not ask for one.
    # ``mock`` is the safe default so DecisionOS runs without credentials.
    default_provider: str = "mock"

    # --- Jev / TypeSafe --------------------------------------------------
    # Primary provider configuration. Values may be supplied under either the
    # JEV_* names or the upstream TYPESAFE_* names.
    jev_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("JEV_API_KEY", "TYPESAFE_API_KEY"),
    )
    jev_base_url: str = Field(
        default="https://api.typesafe.ai",
        validation_alias=AliasChoices("JEV_BASE_URL", "TYPESAFE_BASE_URL"),
    )
    jev_model: str = Field(
        default="jev-latest",
        validation_alias=AliasChoices("JEV_MODEL", "TYPESAFE_DEFAULT_MODEL"),
    )
    jev_timeout_seconds: float = 10.0
    jev_max_retries: int = 3
    jev_backoff_base_seconds: float = 0.5
    jev_backoff_max_seconds: float = 8.0

    # --- Observability ---------------------------------------------------
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "decisionos-api"
    metrics_enabled: bool = True
    trace_sample_ratio: float = 1.0

    @property
    def jev_configured(self) -> bool:
        """Whether a Jev API key is present."""
        return bool(self.jev_api_key.get_secret_value().strip())

    @property
    def auth_enabled(self) -> bool:
        """Authentication is enforced outside of development/test."""
        return self.app_env not in {"development", "test"}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
