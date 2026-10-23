"""How an answer in the channel is read: by a rule, never by guessing (ADR-0008). Pure.

A decision request's answer is read by the decision component's own rule — the option letter
standing alone. This module reads the rest, against the words of the owner's phrasebook:

- the one answer a need, a date or a failure offers — that it is done — is read when the whole
  message is one of the phrasebook's `done_words`;
- a reading sent back is confirmed when the whole message is one of its `yes_words`, and
  rejected when it is one of its `no_words`;
- a request for the live representation of a run or a process is one of its `show_run_words`
  or `show_process_words` followed by one identifier (ADR-0069); a request for the overview is
  one of its `show_overview_words` standing alone;
- a change in dialogue (ADR-0091 §6) and the take-over of a running step (ADR-0128 §7) begin
  with their words and name what they act on; each is read back before it takes effect.

The whole message, not a word in it: a message that negates the word, or says more than it, is
not the word. Case and the punctuation around the word do not count. Anything else is not read,
and is asked back.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from taktus.components.reporting.domain.model import Offered, Phrasebook
from taktus.shared.v1 import Value

_AROUND = " \t\r\n.,;:!?\"'„“”«»()"


def normalised(text: str) -> str:
    return " ".join(text.strip(_AROUND).casefold().split())


def done(text: str, book: Phrasebook) -> bool:
    return normalised(text) in book.done_words


def offer(text: str, offers: Iterable[Offered]) -> str | None:
    """The identifier of the one offered answer whose label is the whole message; None when it
    is none of them. How a reply to the daily report of signals is read (ADR-0109 §6)."""
    said = normalised(text)
    found = [o.id for o in offers if normalised(o.label) == said]
    return found[0] if len(found) == 1 else None


def confirmation(text: str, book: Phrasebook) -> bool | None:
    """True: the reading is confirmed. False: it is rejected. None: the message is neither."""
    said = normalised(text)
    if said in book.yes_words:
        return True
    if said in book.no_words:
        return False
    return None


class Asked(Value):
    """A request for the live representation of the overview, a run or a process (ADR-0069)."""

    level: Literal["overview", "run", "process"]
    id: str = Field(default="", pattern=r"^\S*$")
    """The run's or the process's identifier; empty for the overview, which has none."""
    version: str | None = Field(default=None, min_length=1)
    """For a process: the version named after `@`; None for the active one."""

    @model_validator(mode="after")
    def _named(self) -> Asked:
        if (self.level == "overview") != (self.id == ""):
            raise ValueError("a run or a process is named by its identifier; the overview is not")
        return self


def representation(text: str, book: Phrasebook) -> Asked | None:
    """A message that asks for a representation: one of the phrasebook's words for a run or a
    process, then one identifier, and nothing else. The words are matched as the other words
    are — case and the punctuation around the message do not count; the identifier is taken
    as written. The overview is one of the words standing alone. None for anything else, and
    for a phrasebook that reads no such request."""
    if book.show_run_words is None or book.show_process_words is None:
        return None
    if normalised(text) in (book.show_overview_words or ()):
        return Asked(level="overview")
    tokens = text.strip(_AROUND).split()
    if len(tokens) < 2:
        return None
    said, name = " ".join(tokens[:-1]).casefold(), tokens[-1]
    if said in book.show_run_words:
        return Asked(level="run", id=name)
    if said in book.show_process_words:
        process, at, version = name.rpartition("@")
        if not at:
            return Asked(level="process", id=name)
        if process and version:
            return Asked(level="process", id=process, version=version)
    return None


class Act(Value):
    """A change in dialogue asked for in the owner's conversation (UC-4.15, ADR-0091 §6)."""

    kind: Literal["change", "rehearse", "commission", "rollback"]
    target: str = Field(min_length=1, pattern=r"^\S+$")
    """The process for a change or a rollback; the proposal for a rehearsal or a commissioning."""
    version: str | None = Field(default=None, min_length=1)
    """For a rollback: the version to make current again."""
    words: str | None = Field(default=None, min_length=1)
    """For a change: what should change, in the owner's own words."""


def act(text: str, book: Phrasebook) -> Act | None:
    """A message that asks for a change in dialogue, read by a rule:

    - one of `change_words`, the process, a colon, and the change in the owner's own words;
    - one of `rehearse_words` or `commission_words`, and one proposal's identifier;
    - one of `rollback_words`, and `<process>@<version>`.

    The words are matched as the other words are; identifiers and the owner's words are taken
    as written. None for anything else, and for a phrasebook that reads no change."""
    if book.change_words is None:
        return None
    message = text.strip()
    folded = message.casefold()
    for word in book.change_words:
        if folded.startswith(word + " "):
            process, colon, words = message[len(word) :].strip().partition(":")
            if colon and process.strip() and " " not in process.strip() and words.strip():
                return Act(kind="change", target=process.strip(), words=words.strip())
            return None
    tokens = message.strip(_AROUND).split()
    if len(tokens) < 2:
        return None
    said, name = " ".join(tokens[:-1]).casefold(), tokens[-1]
    if said in (book.rehearse_words or ()):
        return Act(kind="rehearse", target=name)
    if said in (book.commission_words or ()):
        return Act(kind="commission", target=name)
    if said in (book.rollback_words or ()):
        process, at, version = name.rpartition("@")
        if at and process and version:
            return Act(kind="rollback", target=process, version=version)
    return None


class TakeoverAct(Value):
    """The take-over of a running step asked for in the owner's conversation, its hand-back, or
    the question where a take-over stands (UC-4.19, ADR-0128 §7)."""

    kind: Literal["take_over", "hand_back", "show"]
    run: str | None = Field(default=None, pattern=r"^\S+$")
    """For a take-over: the run."""
    step: str | None = Field(default=None, pattern=r"^\S+$")
    """For a take-over: the step."""
    takeover: str | None = Field(default=None, pattern=r"^\S+$")
    """For a hand-back and a question: the take-over identifier."""
    result: str | None = Field(default=None, min_length=1)
    """For a hand-back: the result in the person's own words, as written."""


def takeover_act(text: str, book: Phrasebook) -> TakeoverAct | None:
    """A message that asks for a take-over, read by a rule:

    - one of `takeover_words`, the run's identifier and the step's;
    - one of `hand_back_words`, the take-over's identifier, a colon, and the result;
    - one of `takeover_show_words`, and the take-over's identifier.

    The words are matched as the other words are; identifiers and the result are taken as
    written. None for anything else, and for a phrasebook that reads no take-over."""
    if book.takeover_words is None:
        return None
    message = text.strip()
    folded = message.casefold()
    for word in book.hand_back_words or ():
        if folded.startswith(word + " "):
            takeover, colon, result = message[len(word) :].strip().partition(":")
            if colon and takeover.strip() and " " not in takeover.strip() and result.strip():
                return TakeoverAct(
                    kind="hand_back", takeover=takeover.strip(), result=result.strip()
                )
            return None
    tokens = message.strip(_AROUND).split()
    if len(tokens) >= 2 and " ".join(tokens[:-1]).casefold() in (book.takeover_show_words or ()):
        return TakeoverAct(kind="show", takeover=tokens[-1])
    if len(tokens) >= 3 and " ".join(tokens[:-2]).casefold() in book.takeover_words:
        return TakeoverAct(kind="take_over", run=tokens[-2], step=tokens[-1])
    return None
