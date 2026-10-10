"""How an answer in the channel is read: by a rule, never by guessing (ADR-0008). Pure.

A decision request's answer is read by the decision component's own rule — the option letter
standing alone. This module reads the rest, against the words of the owner's phrasebook:

- the one answer a need, a date or a failure offers — that it is done — is read when the whole
  message is one of the phrasebook's `done_words`;
- a reading sent back is confirmed when the whole message is one of its `yes_words`, and
  rejected when it is one of its `no_words`;
- a request for the live representation of a run or a process is one of its `show_run_words`
  or `show_process_words` followed by one identifier (ADR-0069); a request for the overview is
  one of its `show_overview_words` standing alone.

The whole message, not a word in it: a message that negates the word, or says more than it, is
not the word. Case and the punctuation around the word do not count. Anything else is not read,
and is asked back.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from taktus.components.reporting.domain.model import Phrasebook
from taktus.shared.v1 import Value

_AROUND = " \t\r\n.,;:!?\"'„“”«»()"


def normalised(text: str) -> str:
    return " ".join(text.strip(_AROUND).casefold().split())


def done(text: str, book: Phrasebook) -> bool:
    return normalised(text) in book.done_words


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
