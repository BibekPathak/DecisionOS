"""Unit tests for policy parsing and versioning."""

from __future__ import annotations

import pytest

from decisionos.models import Policy
from decisionos.policies import (
    PolicyNotFoundError,
    PolicyParseError,
    PolicyRegistry,
    load_policy_file,
    load_policy_yaml,
    parse_policy,
)

VALID_YAML = """
name: production-agent-policy
version: 2
rules:
  - name: high-risk
    when:
      risk:
        gt: 0.90
    action:
      require: deny
"""


def test_load_valid_yaml() -> None:
    policy = load_policy_yaml(VALID_YAML)
    assert policy.name == "production-agent-policy"
    assert policy.version == 2
    assert policy.rules[0].name == "high-risk"


def test_version_defaults_to_one() -> None:
    policy = load_policy_yaml(
        "name: p\nrules:\n  - name: r\n    when: {a: 1}\n    action: {require: deny}\n"
    )
    assert policy.version == 1


def test_empty_document_rejected() -> None:
    with pytest.raises(PolicyParseError, match="empty"):
        load_policy_yaml("")


def test_non_mapping_document_rejected() -> None:
    with pytest.raises(PolicyParseError, match="must be a mapping"):
        load_policy_yaml("- just\n- a\n- list\n")


def test_malformed_yaml_rejected() -> None:
    with pytest.raises(PolicyParseError, match="malformed YAML"):
        load_policy_yaml("name: p\nrules: [unclosed")


def test_structurally_invalid_policy_rejected() -> None:
    with pytest.raises(PolicyParseError, match="invalid policy"):
        load_policy_yaml("name: p\nrules: []\n")


def test_parse_policy_rejects_non_mapping() -> None:
    with pytest.raises(PolicyParseError):
        parse_policy(["not", "a", "mapping"])


def test_load_policy_file(tmp_path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(VALID_YAML, encoding="utf-8")
    policy = load_policy_file(path)
    assert policy.name == "production-agent-policy"


def test_load_missing_file_raises() -> None:
    with pytest.raises(PolicyNotFoundError):
        load_policy_file("/nonexistent/policy.yaml")


def test_registry_register_and_resolve_latest() -> None:
    registry = PolicyRegistry()
    v1 = Policy(
        name="p", version=1, rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},)
    )
    v2 = Policy(
        name="p", version=2, rules=({"name": "r", "when": {"a": 2}, "action": {"require": "deny"}},)
    )
    registry.register(v1)
    registry.register(v2)
    assert registry.get("p").version == 2
    assert registry.get("p", 1).version == 1
    assert registry.versions("p") == [1, 2]


def test_registry_unknown_policy_raises() -> None:
    registry = PolicyRegistry()
    with pytest.raises(PolicyNotFoundError):
        registry.get("missing")
    with pytest.raises(PolicyNotFoundError):
        registry.get("missing", 3)


def test_registry_get_by_key() -> None:
    registry = PolicyRegistry()
    v1 = Policy(
        name="p", version=1, rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},)
    )
    registry.register(v1)
    assert registry.get_by_key("p").version == 1
    assert registry.get_by_key("p@1").version == 1
    with pytest.raises(PolicyNotFoundError):
        registry.get_by_key("p@9")
    with pytest.raises(PolicyNotFoundError):
        registry.get_by_key("p@notanumber")


def test_registry_rejects_conflicting_duplicate() -> None:
    registry = PolicyRegistry()
    v1 = Policy(
        name="p", version=1, rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},)
    )
    registry.register(v1)
    different = Policy(
        name="p",
        version=1,
        rules=({"name": "r", "when": {"a": 2}, "action": {"require": "deny"}},),
    )
    with pytest.raises(ValueError, match="already registered"):
        registry.register(different)


def test_registry_identical_duplicate_is_idempotent() -> None:
    registry = PolicyRegistry()
    v1 = Policy(
        name="p", version=1, rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},)
    )
    registry.register(v1)
    registry.register(v1)


def test_registry_lists_names_and_all() -> None:
    registry = PolicyRegistry(
        [
            Policy(
                name="b",
                version=1,
                rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},),
            ),
            Policy(
                name="a",
                version=2,
                rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},),
            ),
            Policy(
                name="a",
                version=1,
                rules=({"name": "r", "when": {"a": 1}, "action": {"require": "deny"}},),
            ),
        ]
    )
    assert registry.names() == ["a", "b"]
    assert [p.key for p in registry.all_policies()] == ["a@1", "a@2", "b@1"]


def test_action_precedence_override() -> None:
    policy = load_policy_yaml(
        """
        name: p
        action_precedence:
          hold: hard_deny
        rules:
          - name: r
            when: {tool: x}
            action: {require: hold}
        """
    )
    from decisionos.models import PolicyPrecedence

    assert policy.precedence_for("hold") is PolicyPrecedence.HARD_DENY


def test_action_precedence_rejects_unknown_action() -> None:
    with pytest.raises(PolicyParseError):
        load_policy_yaml(
            """
            name: p
            action_precedence:
              never_used: hard_deny
            rules:
              - name: r
                when: {tool: x}
                action: {require: deny}
            """
        )
