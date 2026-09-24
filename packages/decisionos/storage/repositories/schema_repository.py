"""Repositories for decision schemas and policies.

Both are immutable and versioned. Each repository also implements the resolver
protocol the engine expects, so a database-backed catalog can be dropped in
where the in-memory one was used.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decisionos.engine.evaluator import SchemaNotFoundError
from decisionos.models import DecisionSchema, Policy
from decisionos.policies.engine import PolicyNotFoundError
from decisionos.storage.models import DecisionSchemaRow, PolicyVersionRow
from decisionos.storage.repositories.mapping import (
    policy_definition,
    policy_to_domain,
    schema_to_domain,
)


class DecisionSchemaRepository:
    """Persistence and resolution for :class:`DecisionSchema`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, schema: DecisionSchema) -> DecisionSchema:
        """Persist a schema version.

        Registering identical content twice is idempotent. Registering
        different content under the same ``name@version`` is rejected, matching
        the in-memory resolver's immutability guarantee.
        """
        existing = await self._get_row(schema.name, schema.version)
        if existing is not None:
            if schema_to_domain(existing) != schema:
                raise ValueError(f"schema {schema.key} already exists with different content")
            return schema_to_domain(existing)

        row = DecisionSchemaRow(
            name=schema.name,
            version=schema.version,
            actions=list(schema.actions),
            action_descriptions=dict(schema.action_descriptions),
            description=schema.description,
            created_at=schema.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return schema_to_domain(row)

    async def get(self, name: str, version: int) -> DecisionSchema:
        row = await self._get_row(name, version)
        if row is None:
            raise SchemaNotFoundError(name, version)
        return schema_to_domain(row)

    async def latest(self, name: str) -> DecisionSchema:
        result = await self._session.execute(
            select(DecisionSchemaRow)
            .where(DecisionSchemaRow.name == name)
            .order_by(DecisionSchemaRow.version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise SchemaNotFoundError(name, 1)
        return schema_to_domain(row)

    async def list_all(self) -> list[DecisionSchema]:
        result = await self._session.execute(
            select(DecisionSchemaRow).order_by(DecisionSchemaRow.name, DecisionSchemaRow.version)
        )
        return [schema_to_domain(row) for row in result.scalars()]

    async def resolve(self, name: str, version: int) -> DecisionSchema:
        """SchemaResolver protocol implementation."""
        return await self.get(name, version)

    async def _get_row(self, name: str, version: int) -> DecisionSchemaRow | None:
        result = await self._session.execute(
            select(DecisionSchemaRow).where(
                DecisionSchemaRow.name == name,
                DecisionSchemaRow.version == version,
            )
        )
        return result.scalar_one_or_none()


class PolicyRepository:
    """Persistence and resolution for :class:`Policy`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, policy: Policy) -> Policy:
        existing = await self._get_row(policy.name, policy.version)
        if existing is not None:
            if policy_to_domain(existing) != policy:
                raise ValueError(f"policy {policy.key} already exists with different content")
            return policy_to_domain(existing)

        row = PolicyVersionRow(
            name=policy.name,
            version=policy.version,
            description=policy.description,
            definition=policy_definition(policy),
        )
        self._session.add(row)
        await self._session.flush()
        return policy_to_domain(row)

    async def get(self, name: str, version: int | None = None) -> Policy:
        if version is not None:
            row = await self._get_row(name, version)
            if row is None:
                raise PolicyNotFoundError(name, version)
            return policy_to_domain(row)
        row = await self._latest_row(name)
        if row is None:
            raise PolicyNotFoundError(name)
        return policy_to_domain(row)

    async def get_by_key(self, key: str) -> Policy:
        if "@" in key:
            name, _, version_text = key.partition("@")
            try:
                version = int(version_text)
            except ValueError as error:
                raise PolicyNotFoundError(key) from error
            return await self.get(name, version)
        return await self.get(key)

    async def list_all(self) -> list[Policy]:
        result = await self._session.execute(
            select(PolicyVersionRow).order_by(PolicyVersionRow.name, PolicyVersionRow.version)
        )
        return [policy_to_domain(row) for row in result.scalars()]

    async def _get_row(self, name: str, version: int) -> PolicyVersionRow | None:
        result = await self._session.execute(
            select(PolicyVersionRow).where(
                PolicyVersionRow.name == name,
                PolicyVersionRow.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def _latest_row(self, name: str) -> PolicyVersionRow | None:
        result = await self._session.execute(
            select(PolicyVersionRow)
            .where(PolicyVersionRow.name == name)
            .order_by(PolicyVersionRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


__all__ = ["DecisionSchemaRepository", "PolicyRepository"]
