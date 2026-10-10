"""An event as a trigger sees it, the catalogue of kinds, and how a filter decides
(`contracts/events/v1`, ADR-0048).

The binding of `Event.json`: `Event` is the root, the catalogue is `KINDS`, `Filter` and
`Condition` are the definitions of those names. `tests/contract` holds the three to the schema.
Matching is a rule over the event alone (ADR-0048 §2): pure, no clock, no other state.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from taktus.shared.v1 import Capability, Value

type ContextValue = str | bool | tuple[str, ...]
type FilterValue = str | bool | tuple[str, ...]


class Kind(StrEnum):
    ISSUE_OPENED = "issue.opened"
    ISSUE_LABELLED = "issue.labelled"
    ISSUE_COMMENT_CREATED = "issue_comment.created"
    PULL_REQUEST_OPENED = "pull_request.opened"
    PIPELINE_RUN_COMPLETED = "pipeline_run.completed"
    BRANCH_PUSHED = "branch.pushed"
    MESSAGE_POSTED = "message.posted"
    MESSAGE_MENTIONED = "message.mentioned"


class Condition(StrEnum):
    CAPACITY_AVAILABLE = "capacity.available"
    """The instance's admission against its platform would admit the run's work now."""


class Fields(Value):
    """The context fields a kind requires, and those it may carry where there is one."""

    required: frozenset[str]
    optional: frozenset[str] = frozenset()

    @property
    def known(self) -> frozenset[str]:
        return self.required | self.optional


_ISSUE = frozenset({"repository", "issue"})
_MESSAGE = Fields(required=frozenset({"conversation", "message"}), optional=frozenset({"thread"}))

KINDS: Mapping[Kind, Fields] = {
    Kind.ISSUE_OPENED: Fields(required=_ISSUE),
    Kind.ISSUE_LABELLED: Fields(required=_ISSUE | {"label"}),
    Kind.ISSUE_COMMENT_CREATED: Fields(required=_ISSUE | {"comment", "is_pull_request"}),
    Kind.PULL_REQUEST_OPENED: Fields(
        required=frozenset({"repository", "pull_request", "head", "base"})
    ),
    Kind.PIPELINE_RUN_COMPLETED: Fields(
        required=frozenset({"repository", "run", "conclusion", "head"}),
        optional=frozenset({"pull_request"}),
    ),
    Kind.BRANCH_PUSHED: Fields(required=frozenset({"repository", "branch", "head", "paths"})),
    Kind.MESSAGE_POSTED: _MESSAGE,
    Kind.MESSAGE_MENTIONED: _MESSAGE,
}
"""The catalogue of v1 (`contracts/events/v1` §2): every kind with the context it requires."""


class Event(Value):
    """One event: an intake the identity component placed, without its sender or its text."""

    id: str = Field(min_length=1)
    kind: Kind
    channel: Capability
    occurred_at: datetime
    received_at: datetime
    context: Mapping[str, ContextValue]

    @staticmethod
    def of(kind: str) -> Kind | None:
        """The catalogue's kind of that name, or None for a kind outside it."""
        try:
            return Kind(kind)
        except ValueError:
            return None

    @staticmethod
    def context_of(raw: Mapping[str, Any]) -> dict[str, ContextValue]:
        """What of an intake's context an event carries: strings, flags and lists of strings.
        Anything else — an object, a number — is the intake's, not the event's."""
        kept: dict[str, ContextValue] = {}
        for name, value in raw.items():
            if isinstance(value, str | bool):
                kept[name] = value
            elif isinstance(value, list | tuple) and all(isinstance(v, str) for v in value):
                kept[name] = tuple(value)
        return kept

    def missing(self) -> list[str]:
        """The fields its kind requires that its context lacks."""
        return sorted(KINDS[self.kind].required - set(self.context))


def holds(entries: Mapping[str, FilterValue] | None, event: Event) -> bool:
    """Whether the filter holds for the event (`contracts/events/v1` §4). Every entry must hold.
    An entry holds when the field's value is one of the values named, or, for a list-valued
    field, when any element is. A field the event does not carry fails its entry."""
    if not entries:
        return True
    for name, wanted in entries.items():
        if name not in event.context:
            return False
        values = wanted if isinstance(wanted, tuple) else (wanted,)
        have = event.context[name]
        elements = have if isinstance(have, tuple) else (have,)
        if not any(element == value for element in elements for value in values):
            return False
    return True
