"""Decision schema definitions.

A ``DecisionSchema`` declares the closed set of actions a decision of a given
type may resolve to. Schemas are versioned and immutable once persisted: a
change in the action set requires creating a new version rather than mutating
an existing one.

The set of actions doubles as the ``criteria`` map sent to a Jev Choice
question, so action names should be stable, machine-readable identifiers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Actions are identifiers, not free text. This keeps them safe to use as
# policy targets and as Jev Choice criteria keys.
_ACTION_MAX_LENGTH = 64


class DecisionSchema(BaseModel):
    """A versioned, typed set of allowed actions for a decision type.

    Attributes
    ----------
    name:
        Stable schema identifier, e.g. ``"ToolAuthorization"``.
    version:
        Monotonic version number, starting at 1.
    actions:
        The closed set of actions a decision may resolve to.
    description:
        Optional human-readable description.
    action_descriptions:
        Optional per-action rubric descriptions used when building the Jev
        Choice ``criteria``. Actions without an entry get a ``None`` rubric.
    created_at:
        When the schema version was created.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    actions: tuple[str, ...] = Field(min_length=1)
    description: str | None = None
    action_descriptions: dict[str, str | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("schema name must not be blank")
        if value != value.strip():
            raise ValueError("schema name must not contain leading or trailing whitespace")
        return value

    @field_validator("actions")
    @classmethod
    def _validate_actions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("a schema must define at least one action")
        seen: set[str] = set()
        for action in value:
            if not action or action != action.strip():
                raise ValueError(f"invalid action name: {action!r}")
            if len(action) > _ACTION_MAX_LENGTH:
                raise ValueError(f"action name exceeds {_ACTION_MAX_LENGTH} characters: {action!r}")
            if action in seen:
                raise ValueError(f"duplicate action: {action!r}")
            seen.add(action)
        return value

    @model_validator(mode="after")
    def _validate_action_descriptions(self) -> DecisionSchema:
        unknown = set(self.action_descriptions) - set(self.actions)
        if unknown:
            raise ValueError(
                f"action_descriptions references actions not in the schema: {sorted(unknown)}"
            )
        return self

    @property
    def key(self) -> str:
        """A stable ``name@version`` identifier."""
        return f"{self.name}@{self.version}"

    def has_action(self, action: str) -> bool:
        """Return whether ``action`` is a member of this schema."""
        return action in self.actions

    def jev_criteria(self) -> dict[str, str | None]:
        """Return the actions as a Jev Choice ``criteria`` map.

        Every action is included, mapped to its optional description. Actions
        without an explicit description map to ``None``, which Jev accepts.
        """
        return {action: self.action_descriptions.get(action) for action in self.actions}


__all__ = ["DecisionSchema"]
