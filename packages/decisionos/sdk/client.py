"""The DecisionOS Python SDK.

Two clients are provided:

* ``AsyncDecisionOS`` — awaitable methods for async applications.
* ``DecisionOS`` — a thin synchronous wrapper for scripts and notebooks.

Both talk to a running DecisionOS API over HTTP. The ergonomic entry point is
:meth:`decide`:

.. code-block:: python

    from decisionos import DecisionOS

    client = DecisionOS("http://localhost:8000")

    decision = await client.decide(
        schema="ToolAuthorization",
        context={"tool": "github.merge", "repository": "production"},
    )

    if decision.action == "allow":
        execute_tool()
    elif decision.action == "human_review":
        request_approval()
    else:
        deny()
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import httpx

from decisionos.sdk.errors import (
    DecisionOSConnectionError,
    error_for_status,
)
from decisionos.sdk.models import (
    CalibrationReport,
    Decision,
    Explanation,
    Outcome,
    Policy,
    Schema,
)

DEFAULT_TIMEOUT = 30.0


class _BaseClient:
    """Shared request logic for the async and sync clients."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._external_client = client

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        body = self._decode(response)
        detail = None
        retry_after = None
        if isinstance(body, dict):
            detail = body.get("detail")
        if response.status_code == 429:
            header = response.headers.get("retry-after")
            if header:
                try:
                    retry_after = float(header)
                except ValueError:
                    retry_after = None
        error = error_for_status(
            response.status_code,
            detail=detail,
            body=body,
            request_id=response.headers.get("x-request-id"),
        )
        if retry_after is not None:
            error.retry_after = retry_after  # type: ignore[attr-defined]
        raise error


class AsyncDecisionOS(_BaseClient):
    """Asynchronous DecisionOS client."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(base_url, api_key=api_key, timeout=timeout, client=client)
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def __aenter__(self) -> AsyncDecisionOS:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client (unless it was supplied)."""
        if self._external_client is None:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method, path, json=json, params=params, headers=self._headers(headers)
            )
        except httpx.HTTPError as error:
            raise DecisionOSConnectionError(str(error)) from error
        self._raise_for_response(response)
        return response

    # -- decisions --------------------------------------------------------

    async def decide(
        self,
        *,
        schema: str,
        context: Mapping[str, Any],
        schema_version: int = 1,
        decision_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        provider: str | None = None,
        policy: str | None = None,
        idempotency_key: str | None = None,
    ) -> Decision:
        """Make a decision and return it.

        ``schema`` names the ``DecisionSchema``; ``context`` is the structured
        state to evaluate. ``decision_type`` defaults to a snake_case form of
        the schema name.
        """
        body = _decision_body(
            schema=schema,
            context=context,
            schema_version=schema_version,
            decision_type=decision_type,
            metadata=metadata,
            provider=provider,
            policy=policy,
        )
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        response = await self._request("POST", "/v1/decisions", json=body, headers=headers)
        return Decision.model_validate(response.json())

    async def get_decision(self, decision_id: str) -> Decision:
        """Fetch a decision by id."""
        response = await self._request("GET", f"/v1/decisions/{decision_id}")
        return Decision.model_validate(response.json())

    async def list_decisions(
        self,
        *,
        decision_type: str | None = None,
        schema_name: str | None = None,
        schema_version: int | None = None,
        provider: str | None = None,
        action: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Decision]:
        """List decisions, optionally filtered."""
        params = _drop_none(
            {
                "decision_type": decision_type,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "provider": provider,
                "action": action,
                "state": state,
                "limit": limit,
                "offset": offset,
            }
        )
        response = await self._request("GET", "/v1/decisions", params=params)
        return [Decision.model_validate(item) for item in response.json()]

    async def record_outcome(
        self,
        decision_id: str,
        *,
        actual_outcome: str,
        success: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> Outcome:
        """Record the observed outcome of a decision."""
        body = {
            "actual_outcome": actual_outcome,
            "success": success,
            "metadata": dict(metadata or {}),
        }
        response = await self._request("POST", f"/v1/decisions/{decision_id}/outcome", json=body)
        return Outcome.model_validate(response.json())

    async def explain(self, decision_id: str) -> Explanation:
        """Return structured evidence for a decision."""
        response = await self._request("GET", f"/v1/decisions/{decision_id}/explanation")
        return Explanation.model_validate(response.json())

    # -- schemas ----------------------------------------------------------

    async def register_schema(
        self,
        *,
        name: str,
        actions: list[str],
        version: int = 1,
        description: str | None = None,
        action_descriptions: Mapping[str, str | None] | None = None,
    ) -> Schema:
        """Register a decision schema version."""
        body = {
            "name": name,
            "version": version,
            "actions": actions,
            "description": description,
            "action_descriptions": dict(action_descriptions or {}),
        }
        response = await self._request("POST", "/v1/schemas", json=body)
        return Schema.model_validate(response.json())

    async def list_schemas(self) -> list[Schema]:
        """List decision schemas."""
        response = await self._request("GET", "/v1/schemas")
        return [Schema.model_validate(item) for item in response.json()]

    async def get_schema(self, name: str, version: int) -> Schema:
        """Fetch a schema version."""
        response = await self._request("GET", f"/v1/schemas/{name}/{version}")
        return Schema.model_validate(response.json())

    # -- policies ---------------------------------------------------------

    async def register_policy(
        self,
        *,
        name: str,
        rules: list[dict[str, Any]],
        version: int = 1,
        description: str | None = None,
        action_precedence: Mapping[str, str] | None = None,
    ) -> Policy:
        """Register a policy version."""
        body: dict[str, Any] = {
            "name": name,
            "version": version,
            "rules": rules,
            "description": description,
        }
        if action_precedence:
            body["action_precedence"] = dict(action_precedence)
        response = await self._request("POST", "/v1/policies", json=body)
        return Policy.model_validate(response.json())

    async def list_policies(self) -> list[Policy]:
        """List policies."""
        response = await self._request("GET", "/v1/policies")
        return [Policy.model_validate(item) for item in response.json()]

    async def get_policy(self, key: str) -> Policy:
        """Fetch a policy by ``name`` or ``name@version``."""
        response = await self._request("GET", f"/v1/policies/{key}")
        return Policy.model_validate(response.json())

    # -- calibration ------------------------------------------------------

    async def calibration(
        self,
        *,
        decision_type: str | None = None,
        schema_name: str | None = None,
        schema_version: int | None = None,
        provider: str | None = None,
        action: str | None = None,
    ) -> CalibrationReport:
        """Return a calibration report, optionally filtered."""
        params = _drop_none(
            {
                "decision_type": decision_type,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "provider": provider,
                "action": action,
            }
        )
        response = await self._request("GET", "/v1/calibration", params=params)
        return CalibrationReport.model_validate(response.json())

    # -- ops --------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return the server's health payload."""
        response = await self._request("GET", "/health")
        return response.json()


class DecisionOS(_BaseClient):
    """Synchronous DecisionOS client.

    A thin wrapper over :class:`AsyncDecisionOS` that runs each call to
    completion. Use :class:`AsyncDecisionOS` in async code.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(base_url, api_key=api_key, timeout=timeout, client=client)
        self._client = client or httpx.Client(base_url=self._base_url, timeout=timeout)

    def __enter__(self) -> DecisionOS:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client (unless it was supplied)."""
        if self._external_client is None:
            self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = self._client.request(
                method, path, json=json, params=params, headers=self._headers(headers)
            )
        except httpx.HTTPError as error:
            raise DecisionOSConnectionError(str(error)) from error
        self._raise_for_response(response)
        return response

    # The sync surface mirrors the async surface, building the same requests
    # and parsing the same responses with the synchronous HTTP client.
    def decide(
        self,
        *,
        schema: str,
        context: Mapping[str, Any],
        schema_version: int = 1,
        decision_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        provider: str | None = None,
        policy: str | None = None,
        idempotency_key: str | None = None,
    ) -> Decision:
        body = _decision_body(
            schema=schema,
            context=context,
            schema_version=schema_version,
            decision_type=decision_type,
            metadata=metadata,
            provider=provider,
            policy=policy,
        )
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        response = self._request("POST", "/v1/decisions", json=body, headers=headers)
        return Decision.model_validate(response.json())

    def get_decision(self, decision_id: str) -> Decision:
        response = self._request("GET", f"/v1/decisions/{decision_id}")
        return Decision.model_validate(response.json())

    def list_decisions(
        self,
        *,
        decision_type: str | None = None,
        schema_name: str | None = None,
        schema_version: int | None = None,
        provider: str | None = None,
        action: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Decision]:
        params = _drop_none(
            {
                "decision_type": decision_type,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "provider": provider,
                "action": action,
                "state": state,
                "limit": limit,
                "offset": offset,
            }
        )
        response = self._request("GET", "/v1/decisions", params=params)
        return [Decision.model_validate(item) for item in response.json()]

    def record_outcome(
        self,
        decision_id: str,
        *,
        actual_outcome: str,
        success: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> Outcome:
        body = {
            "actual_outcome": actual_outcome,
            "success": success,
            "metadata": dict(metadata or {}),
        }
        response = self._request("POST", f"/v1/decisions/{decision_id}/outcome", json=body)
        return Outcome.model_validate(response.json())

    def explain(self, decision_id: str) -> Explanation:
        response = self._request("GET", f"/v1/decisions/{decision_id}/explanation")
        return Explanation.model_validate(response.json())

    def register_schema(
        self,
        *,
        name: str,
        actions: list[str],
        version: int = 1,
        description: str | None = None,
        action_descriptions: Mapping[str, str | None] | None = None,
    ) -> Schema:
        body = {
            "name": name,
            "version": version,
            "actions": actions,
            "description": description,
            "action_descriptions": dict(action_descriptions or {}),
        }
        response = self._request("POST", "/v1/schemas", json=body)
        return Schema.model_validate(response.json())

    def list_schemas(self) -> list[Schema]:
        response = self._request("GET", "/v1/schemas")
        return [Schema.model_validate(item) for item in response.json()]

    def get_schema(self, name: str, version: int) -> Schema:
        response = self._request("GET", f"/v1/schemas/{name}/{version}")
        return Schema.model_validate(response.json())

    def register_policy(
        self,
        *,
        name: str,
        rules: list[dict[str, Any]],
        version: int = 1,
        description: str | None = None,
        action_precedence: Mapping[str, str] | None = None,
    ) -> Policy:
        body: dict[str, Any] = {
            "name": name,
            "version": version,
            "rules": rules,
            "description": description,
        }
        if action_precedence:
            body["action_precedence"] = dict(action_precedence)
        response = self._request("POST", "/v1/policies", json=body)
        return Policy.model_validate(response.json())

    def list_policies(self) -> list[Policy]:
        response = self._request("GET", "/v1/policies")
        return [Policy.model_validate(item) for item in response.json()]

    def get_policy(self, key: str) -> Policy:
        response = self._request("GET", f"/v1/policies/{key}")
        return Policy.model_validate(response.json())

    def calibration(
        self,
        *,
        decision_type: str | None = None,
        schema_name: str | None = None,
        schema_version: int | None = None,
        provider: str | None = None,
        action: str | None = None,
    ) -> CalibrationReport:
        params = _drop_none(
            {
                "decision_type": decision_type,
                "schema_name": schema_name,
                "schema_version": schema_version,
                "provider": provider,
                "action": action,
            }
        )
        response = self._request("GET", "/v1/calibration", params=params)
        return CalibrationReport.model_validate(response.json())

    def health(self) -> dict[str, Any]:
        response = self._request("GET", "/health")
        return response.json()


def _decision_body(
    *,
    schema: str,
    context: Mapping[str, Any],
    schema_version: int,
    decision_type: str | None,
    metadata: Mapping[str, Any] | None,
    provider: str | None,
    policy: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "decision_type": decision_type or _snake_case(schema),
        "schema_name": schema,
        "schema_version": schema_version,
        "context": dict(context),
        "metadata": dict(metadata or {}),
    }
    if provider is not None:
        body["provider"] = provider
    if policy is not None:
        body["policy"] = policy
    return body


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _drop_none(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


__all__ = ["AsyncDecisionOS", "DecisionOS"]
