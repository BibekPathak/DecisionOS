"""Policy loading and versioning.

Policies are authored as YAML, parsed into the validated :class:`Policy`
model, and registered in a :class:`PolicyRegistry`. Versioning mirrors decision
schemas: a policy version is immutable once registered, and a change to the
rules requires a new version.

YAML shape (the ``version`` key is optional and defaults to 1)::

    name: production-agent-policy
    version: 1
    rules:
      - name: dangerous-database-operation
        when:
          tool: database.delete
        action:
          require: deny

      - name: high-risk
        when:
          risk:
            gt: 0.90
        action:
          require: deny
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from decisionos.models import Policy


class PolicyParseError(ValueError):
    """Raised when a policy document cannot be parsed or validated."""


class PolicyNotFoundError(LookupError):
    """Raised when a requested policy or version does not exist."""

    def __init__(self, name: str, version: int | None = None) -> None:
        target = name if version is None else f"{name}@{version}"
        super().__init__(f"policy {target!r} not found")
        self.name = name
        self.version = version


def parse_policy(data: object, *, source: str = "<string>") -> Policy:
    """Validate a parsed YAML mapping as a :class:`Policy`."""
    if not isinstance(data, dict):
        raise PolicyParseError(f"{source}: policy document must be a mapping")
    payload = dict(data)
    payload.setdefault("version", 1)
    try:
        return Policy.model_validate(payload)
    except ValidationError as error:
        raise PolicyParseError(f"{source}: invalid policy: {error}") from error


def load_policy_yaml(text: str, *, source: str = "<string>") -> Policy:
    """Parse and validate a policy from a YAML string."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise PolicyParseError(f"{source}: malformed YAML: {error}") from error
    raise_if_empty(data, source)
    return parse_policy(data, source=source)


def load_policy_file(path: str | Path) -> Policy:
    """Parse and validate a policy from a YAML file."""
    path = Path(path)
    if not path.is_file():
        raise PolicyNotFoundError(str(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PolicyParseError(f"{path}: could not read file: {error}") from error
    return load_policy_yaml(text, source=str(path))


def raise_if_empty(data: object, source: str) -> None:
    if data is None:
        raise PolicyParseError(f"{source}: policy document is empty")


class PolicyRegistry:
    """An in-memory, versioned catalog of policies.

    Phase 5 provides a database-backed equivalent; the API is identical.
    """

    def __init__(self, policies: list[Policy] | None = None) -> None:
        self._policies: dict[tuple[str, int], Policy] = {}
        for policy in policies or []:
            self.register(policy)

    def register(self, policy: Policy) -> None:
        """Register a policy version.

        Raises
        ------
        ValueError
            If the same ``name@version`` is already registered with different
            content. Registering identical content is idempotent.
        """
        key = (policy.name, policy.version)
        existing = self._policies.get(key)
        if existing is not None and existing != policy:
            raise ValueError(f"policy {policy.key} already registered with different content")
        self._policies[key] = policy

    def get(self, name: str, version: int | None = None) -> Policy:
        """Resolve a policy by name and optional version.

        When ``version`` is ``None`` the highest registered version is
        returned. Raises :class:`PolicyNotFoundError` if nothing matches.
        """
        if version is not None:
            policy = self._policies.get((name, version))
            if policy is None:
                raise PolicyNotFoundError(name, version)
            return policy
        versions = [v for (n, v) in self._policies if n == name]
        if not versions:
            raise PolicyNotFoundError(name)
        return self._policies[(name, max(versions))]

    def get_by_key(self, key: str) -> Policy:
        """Resolve a policy from a ``name`` or ``name@version`` string."""
        if "@" in key:
            name, _, version_text = key.partition("@")
            try:
                version = int(version_text)
            except ValueError as error:
                raise PolicyNotFoundError(key) from error
            return self.get(name, version)
        return self.get(key)

    def versions(self, name: str) -> list[int]:
        """Return the registered versions for ``name``, ascending."""
        return sorted(v for (n, v) in self._policies if n == name)

    def names(self) -> list[str]:
        """Return the distinct registered policy names."""
        return sorted({name for (name, _) in self._policies})

    def all_policies(self) -> list[Policy]:
        """Return every registered policy, ordered by name then version."""
        return [self._policies[key] for key in sorted(self._policies)]


__all__ = [
    "PolicyNotFoundError",
    "PolicyParseError",
    "PolicyRegistry",
    "load_policy_file",
    "load_policy_yaml",
    "parse_policy",
    "raise_if_empty",
]
