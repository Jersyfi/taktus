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
from typing import Any

from pydantic import Field, model_validator

from taktus.shared.v1 import Capability, Value

PLACEHOLDERS: dict[str, frozenset[str]] = {
    "answer_with": frozenset({"answers"}),
    "reflect": frozenset({"answer", "label"}),
    "confirm": frozenset({"yes", "no"}),
    "asked_back": frozenset({"answers"}),
    "filed": frozenset({"answer"}),
    "change_started": frozenset({"process", "run"}),
    "rehearsing": frozenset({"proposal", "run"}),
    "commission_read": frozenset({"proposal", "process", "version"}),
    "rollback_read": frozenset({"process", "version"}),
    "commissioned": frozenset({"process", "version"}),
    "rolled_back": frozenset({"process", "version", "new"}),
    "intervene": frozenset({"process"}),
    "intervened": frozenset({"process", "run"}),
    "takeover_read": frozenset({"run", "step"}),
    "takeover_asked": frozenset({"takeover", "run", "step"}),
    "takeover_waiting": frozenset({"takeover", "step"}),
    "takeover_state": frozenset(
        {
            "takeover",
            "run",
            "step",
            "until",
            "goal",
            "acceptance",
            "inputs",
            "checkpoint",
            "produced",
        }
    ),
    "takeover_refused": frozenset({"takeover", "step"}),
    "takeover_lapsed": frozenset({"takeover", "step"}),
    "takeover_handed": frozenset({"takeover", "step"}),
    "hand_back_read": frozenset({"takeover", "run", "step", "form"}),
    "handed_back": frozenset({"run", "step"}),
    "spend_of_run": frozenset({"run"}),
    "spend_against": frozenset({"run", "other"}),
    "spend_of_process": frozenset({"process", "days", "runs"}),
    "spend_line": frozenset({"step", "money", "takte", "tokens_in", "tokens_out", "turns"}),
    "spend_compared": frozenset({"step", "left", "right", "result"}),
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
    show_overview_words: tuple[str, ...] | None = None
    """The words that, standing alone, ask for the overview. None: the channel reads no such
    request — a phrasebook configured before there were any. Given only with the four entries
    of a run and a process (ADR-0069 §5)."""
    live: str | None = Field(default=None, min_length=1)
    """The label of the link to the live representation in the web app."""
    not_shown: str | None = Field(default=None, min_length=1)
    """Said when nothing of that name can be shown to whoever asked: the same whether it does
    not exist or they may not see it."""
    change_words: tuple[str, ...] | None = None
    """The words a change in dialogue begins with, before `<process>:` and the change in the
    owner's own words (UC-4.15, ADR-0091 §6). None: the channel reads no change — a phrasebook
    configured before there were any."""
    rehearse_words: tuple[str, ...] | None = None
    """The words before a proposal's identifier that ask for its rehearsal."""
    commission_words: tuple[str, ...] | None = None
    """The words before a proposal's identifier that ask to commission it; read back first."""
    rollback_words: tuple[str, ...] | None = None
    """The words before `<process>@<version>` that ask to roll back to it; read back first."""
    change_started: str | None = Field(default=None, min_length=1)
    rehearsing: str | None = Field(default=None, min_length=1)
    commission_read: str | None = Field(default=None, min_length=1)
    rollback_read: str | None = Field(default=None, min_length=1)
    commissioned: str | None = Field(default=None, min_length=1)
    rolled_back: str | None = Field(default=None, min_length=1)
    act_refused: str | None = Field(default=None, min_length=1)
    """Said when a change, a rehearsal, a commissioning or a rollback cannot be done; the web
    app's page of the process says why."""
    signals: str | None = Field(default=None, min_length=1)
    """The heading of the daily report of signals (ADR-0109). None: the title alone."""
    intervene: str | None = Field(default=None, min_length=1)
    """The label of an intervention the daily report offers, with `{process}`: what a person
    answers to start it. None: the report offers none."""
    intervened: str | None = Field(default=None, min_length=1)
    """Said when a confirmed intervention started, with `{process}` and `{run}`."""
    takeover_words: tuple[str, ...] | None = None
    """The words before `<run> <step>` that ask to take over a running step (UC-4.19, ADR-0128
    §7); read back first. None: the channel reads no take-over — a phrasebook configured before
    there were any."""
    hand_back_words: tuple[str, ...] | None = None
    """The words before `<takeover>:` and the result, which hand the result back; read back
    first."""
    takeover_show_words: tuple[str, ...] | None = None
    """The words before a take-over's identifier that ask where it stands, and for its state."""
    takeover_read: str | None = Field(default=None, min_length=1)
    takeover_asked: str | None = Field(default=None, min_length=1)
    takeover_waiting: str | None = Field(default=None, min_length=1)
    """Said of a take-over asked and not served yet: the worker has not reached its boundary."""
    takeover_state: str | None = Field(default=None, min_length=1)
    """The state a step was taken over in, in words, while it is held (ADR-0128 §3)."""
    takeover_refused: str | None = Field(default=None, min_length=1)
    """Said of a take-over whose step ended another way before it stopped."""
    takeover_lapsed: str | None = Field(default=None, min_length=1)
    """Said of a take-over whose lease passed without a hand-back: the step went back."""
    takeover_handed: str | None = Field(default=None, min_length=1)
    """Said of a take-over whose result was handed back."""
    hand_back_read: str | None = Field(default=None, min_length=1)
    as_json: str | None = Field(default=None, min_length=1)
    """`{form}` of `hand_back_read` for a result that is read as JSON."""
    as_text: str | None = Field(default=None, min_length=1)
    """`{form}` of `hand_back_read` for a result that is read as the text written."""
    handed_back: str | None = Field(default=None, min_length=1)
    takeover_not_done: str | None = Field(default=None, min_length=1)
    """Said when a take-over or a hand-back cannot be done, or concerns nothing the person may
    see; the run's page in the web app says why."""

    spend_words: tuple[str, ...] | None = None
    """The words before `<run>`, or `<run> <other run>`, that ask where a run spent, step by
    step, or two runs side by side (#449, ADR-0148). None: the channel reads no such request — a
    phrasebook configured before there were any."""
    spend_process_words: tuple[str, ...] | None = None
    """The words before `<process>` that ask where a process spent over the last thirty days."""
    spend_of_run: str | None = Field(default=None, min_length=1)
    spend_against: str | None = Field(default=None, min_length=1)
    spend_of_process: str | None = Field(default=None, min_length=1)
    spend_line: str | None = Field(default=None, min_length=1)
    """One step's figures: its money, its Takte, its tokens in and out, its turns."""
    spend_compared: str | None = Field(default=None, min_length=1)
    """One step of two runs: each side's figures, and whether the results are the same."""
    not_priced: str | None = Field(default=None, min_length=1)
    """Said where money or Takte could not be computed: never counted as nothing."""
    same_result: str | None = Field(default=None, min_length=1)
    other_result: str | None = Field(default=None, min_length=1)

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
            "show_overview_words": self.show_overview_words or (),
            "change_words": self.change_words or (),
            "rehearse_words": self.rehearse_words or (),
            "commission_words": self.commission_words or (),
            "rollback_words": self.rollback_words or (),
            "takeover_words": self.takeover_words or (),
            "hand_back_words": self.hand_back_words or (),
            "takeover_show_words": self.takeover_show_words or (),
            "spend_words": self.spend_words or (),
            "spend_process_words": self.spend_process_words or (),
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
        if self.show_overview_words is not None and not (self.show_overview_words and all(showing)):
            problems.append(
                "show_overview_words are given with show_run_words, show_process_words, live "
                "and not_shown, and name at least one word"
            )
        asking = (
            set(self.show_run_words or ()),
            set(self.show_process_words or ()),
            set(self.show_overview_words or ()),
        )
        if any(a & b for i, a in enumerate(asking) for b in asking[i + 1 :]):
            problems.append("a word cannot ask for two levels")
        changing = (
            self.change_words,
            self.rehearse_words,
            self.commission_words,
            self.rollback_words,
            self.change_started,
            self.rehearsing,
            self.commission_read,
            self.rollback_read,
            self.commissioned,
            self.rolled_back,
            self.act_refused,
        )
        if any(x is not None for x in changing) and any(not x for x in changing):
            problems.append(
                "a phrasebook that reads a change in dialogue names every one of its eleven "
                "entries, from change_words to act_refused (ADR-0091 §6)"
            )
        taking = (
            self.takeover_words,
            self.hand_back_words,
            self.takeover_show_words,
            self.takeover_read,
            self.takeover_asked,
            self.takeover_waiting,
            self.takeover_state,
            self.takeover_refused,
            self.takeover_lapsed,
            self.takeover_handed,
            self.hand_back_read,
            self.as_json,
            self.as_text,
            self.handed_back,
            self.takeover_not_done,
        )
        if any(x is not None for x in taking) and any(not x for x in taking):
            problems.append(
                "a phrasebook that reads a take-over names every one of its fifteen entries, "
                "from takeover_words to takeover_not_done (ADR-0128 §7)"
            )
        spending = (
            self.spend_words,
            self.spend_process_words,
            self.spend_of_run,
            self.spend_against,
            self.spend_of_process,
            self.spend_line,
            self.spend_compared,
            self.not_priced,
            self.same_result,
            self.other_result,
        )
        if any(x is not None for x in spending) and any(not x for x in spending):
            problems.append(
                "a phrasebook that reads a request for spend names every one of its ten "
                "entries, from spend_words to other_result (ADR-0148)"
            )
        if set(self.spend_words or ()) & set(self.spend_process_words or ()):
            problems.append("a word cannot ask for the spend of a run and of a process")
        acting = [
            set(words or ())
            for words in (
                self.change_words,
                self.rehearse_words,
                self.commission_words,
                self.rollback_words,
                self.takeover_words,
                self.hand_back_words,
                self.takeover_show_words,
            )
        ]
        if any(a & b for i, a in enumerate(acting) for b in acting[i + 1 :]):
            problems.append("a word cannot ask for two acts")
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


class PendingAct(Value):
    """An act asked for in the owner's conversation, read back and waiting for its confirmation
    (ADR-0008): a commissioning or a rollback (ADR-0091 §6), or the take-over of a running step
    and its hand-back (ADR-0128 §7). Stored under its conversation and thread, so that the next
    `yes` there confirms it; never deleted, only moved to `done` or `dropped`. A take-over that
    was asked is kept once more under its own identifier, so that its state is shown and its
    result handed back from any thread of the conversation."""

    id: str = Field(min_length=1)
    """`<address>:<thread>`: one act waits per thread. For a take-over asked: its identifier."""
    tenant: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(commission|rollback|take_over|hand_back)$")
    process: str | None = Field(default=None, min_length=1)
    """For a commissioning or a rollback: the process."""
    proposal: str | None = None
    version: str | None = Field(default=None, min_length=1)
    """The version a commissioning makes active, or the one a rollback makes current again."""
    run: str | None = Field(default=None, min_length=1)
    """For a take-over and a hand-back: the run."""
    step: str | None = Field(default=None, min_length=1)
    """For a take-over and a hand-back: the step."""
    takeover: str | None = Field(default=None, min_length=1)
    """For a hand-back, and for a take-over once it was asked: the take-over identifier."""
    result: Any = None
    """For a hand-back: the result as it was read — a JSON value, or the text as written."""
    by: str = Field(min_length=1)
    """Who asked; only the same person confirms it."""
    state: str = Field(default="awaiting", pattern=r"^(awaiting|done|dropped)$")
    asked_at: datetime

    @model_validator(mode="after")
    def _named(self) -> PendingAct:
        if self.kind in ("commission", "rollback") and (not self.process or not self.version):
            raise ValueError(f"a {self.kind} names its process and its version")
        if self.kind in ("take_over", "hand_back") and (not self.run or not self.step):
            raise ValueError(f"a {self.kind} names its run and its step")
        if self.kind == "hand_back" and not self.takeover:
            raise ValueError("a hand-back names its take-over")
        return self
