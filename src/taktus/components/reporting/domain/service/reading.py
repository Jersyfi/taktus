"""How an answer in the channel is read: by a rule, never by guessing (ADR-0008). Pure.

A decision request's answer is read by the decision component's own rule — the option letter
standing alone. This module reads the rest, against the words of the owner's phrasebook:

- the one answer a need, a date or a failure offers — that it is done — is read when the whole
  message is one of the phrasebook's `done_words`;
- a reading sent back is confirmed when the whole message is one of its `yes_words`, and
  rejected when it is one of its `no_words`.

The whole message, not a word in it: a message that negates the word, or says more than it, is
not the word. Case and the punctuation around the word do not count. Anything else is not read,
and is asked back.
"""

from __future__ import annotations

from taktus.components.reporting.domain.model import Phrasebook

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
