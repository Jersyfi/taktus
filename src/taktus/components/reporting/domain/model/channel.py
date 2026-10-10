"""The owner-facing channel of a tenant: configuration, never architecture (ADR-0045).

A tenant names **who its owner is** — an identity — and **whom the owner named** to answer in
their place. It names **where a report goes**: a channel a connector serves and the address in
it, and optionally a ticket system, as a connector's capability and operation. And it names
**the owner's language**, as a phrasebook: every sentence Taktus says to the owner, with the
words it reads an answer by.

The core names no language. A phrasebook is data the tenant configures; the ones Taktus ships
are files beside the composition root, never text in a component.
"""

from __future__ import annotations

from datetime import datetime
from string import Formatter

from pydantic import Field, model_validator

from taktus.shared.v1 import Capability, Value

PLACEHOLDERS: dict[str, frozenset[str]] = {
    "answer_with": frozenset({"answers"}),
    "reflect": frozenset({"answer", "label"}),
    "confirm": frozenset({"yes", "no"}),
    "asked_back": frozenset({"answers"}),
    "filed": frozenset({"answer"}),
}
"""The sentences that take values, and the values each must use — no more, no fewer."""


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name is not None}


class Phrasebook(Value):
    """Every sentence the owner reads, in their language."""

    language: str = Field(min_length=1)
    """The language as a tag (BCP 47), for whoever reads the configuration."""
    decision: str = Field(min_length=1)
    need: str = Field(min_length=1)
    date: str = Field(min_length=1)
    failure: str = Field(min_length=1)
    needed: str = Field(min_length=1)
    steps: str = Field(min_length=1)
    standing_still: str = Field(min_length=1)
    due: str = Field(min_length=1)
    links: str = Field(min_length=1)
    task: str = Field(min_length=1)
    """The label of the link to the task in the ticket system."""
    view: str = Field(min_length=1)
    """The label of the link to the report's view."""
    answer_with: str = Field(min_length=1)
    recommended: str = Field(min_length=1)
    """The word that marks the option a decision request recommends."""
    done: str = Field(min_length=1)
    """The one answer a need, a date or a failure offers: that it is done."""
    done_words: tuple[str, ...] = Field(min_length=1)
    yes_words: tuple[str, ...] = Field(min_length=1)
    no_words: tuple[str, ...] = Field(min_length=1)
    reflect: str = Field(min_length=1)
    kept: str = Field(min_length=1)
    confirm: str = Field(min_length=1)
    asked_back: str = Field(min_length=1)
    filed: str = Field(min_length=1)
    reread: str = Field(min_length=1)
    not_filed: str = Field(min_length=1)
    closed: str = Field(min_length=1)
    """Said to whoever answers a report that is filed already: nothing changes."""
    show_run_words: tuple[str, ...] | None = None
    """The words a request for the representation of a run begins with, before the run's
    identifier (UC-6.10 *beyond the web app*, ADR-0069). None: the channel reads no such
    request — a phrasebook configured before there were any."""
    show_process_words: tuple[str, ...] | None = None
    """The same for a process, before `<process>` or `<process>@<version>`."""
    live: str | None = Field(default=None, min_length=1)
    """The label of the link to the live representation in the web app."""
    not_shown: str | None = Field(default=None, min_length=1)
    """Said when nothing of that name can be shown to whoever asked: the same whether it does
    not exist or they may not see it."""

    @model_validator(mode="after")
    def _readable(self) -> Phrasebook:
        problems: list[str] = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if not isinstance(value, str):
                continue
            used = _placeholders(value)
            allowed = PLACEHOLDERS.get(name, frozenset())
            if used != allowed:
                problems.append(f"{name} uses {sorted(used)}; it must use {sorted(allowed)}")
        words = {
            "done_words": self.done_words,
            "yes_words": self.yes_words,
            "no_words": self.no_words,
            "show_run_words": self.show_run_words or (),
            "show_process_words": self.show_process_words or (),
        }
        for name, listed in words.items():
            if any(w != w.strip().casefold() or not w for w in listed):
                problems.append(f"{name} are written in lower case, without spaces around them")
        if set(self.yes_words) & set(self.no_words):
            problems.append("a word cannot both confirm and reject")
        showing = (self.show_run_words, self.show_process_words, self.live, self.not_shown)
        if any(x is not None for x in showing) and any(not x for x in showing):
            problems.append(
                "a phrasebook that reads a request for a representation names show_run_words, "
                "show_process_words, live and not_shown, all four"
            )
        if set(self.show_run_words or ()) & set(self.show_process_words or ()):
            problems.append("a word cannot ask for both a run and a process")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class TaskDestination(Value):
    """A ticket system: the connector capability that serves it and the operation that opens a
    task there, with `title` and `body`."""

    capability: Capability
    operation: str = Field(min_length=1)


class OwnerChannel(Value):
    """One tenant's owner-facing channel, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    """The owner's identity."""
    named: tuple[str, ...] = ()
    """The identities the owner named to answer in their place."""
    roles: tuple[str, ...] = Field(default=("owner",), min_length=1)
    """The decision requests addressed to one of these roles go to the owner."""
    channel: Capability
    """The channel a connector serves; a report is said there through its reply operation."""
    address: str = Field(min_length=1)
    """Where in that channel: the conversation with the owner."""
    phrasebook: Phrasebook
    task: TaskDestination | None = None
    view_base: str | None = Field(default=None, min_length=1)
    """The address the control plane is reached at; every message then links the report's
    view. None: no link to the view."""
    configured_at: datetime
    configured_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _stored_under_its_tenant(self) -> OwnerChannel:
        if self.id != self.tenant:
            raise ValueError(f"a channel is stored under its tenant {self.tenant!r}")
        if self.owner in self.named:
            raise ValueError("the owner answers as the owner, not as someone named")
        return self

    def may_answer(self, identity: str | None) -> bool:
        """Only the owner, or someone the owner named (UC-1.7)."""
        return identity is not None and (identity == self.owner or identity in self.named)
