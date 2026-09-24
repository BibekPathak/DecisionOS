"""Unit tests for API-key authentication.

Auth is disabled in development/test; these tests force ``app_env=production``
with a configured key to exercise enforcement. The app is built without a
lifespan (no database) by overriding ``app.state`` directly.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.dependencies import require_api_key
from decisionos.config import Settings


def _client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.state.settings = settings

    @app.get("/protected")
    async def protected(_: None = Depends(require_api_key)) -> dict[str, str]:
        return {"ok": "true"}

    return TestClient(app)


def _production_settings(api_key: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        api_key=api_key,
    )


def test_auth_disabled_in_development() -> None:
    client = _client(Settings(_env_file=None, app_env="development", api_key=""))
    assert client.get("/protected").status_code == 200


def test_auth_accepts_x_api_key_header() -> None:
    client = _client(_production_settings("secret-key"))
    response = client.get("/protected", headers={"X-API-Key": "secret-key"})
    assert response.status_code == 200


def test_auth_accepts_bearer_token() -> None:
    client = _client(_production_settings("secret-key"))
    response = client.get("/protected", headers={"Authorization": "Bearer secret-key"})
    assert response.status_code == 200


def test_auth_rejects_missing_key() -> None:
    client = _client(_production_settings("secret-key"))
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_auth_rejects_wrong_key() -> None:
    client = _client(_production_settings("secret-key"))
    response = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_auth_fails_closed_when_key_not_configured() -> None:
    client = _client(_production_settings(""))
    response = client.get("/protected", headers={"X-API-Key": "anything"})
    assert response.status_code == 503
