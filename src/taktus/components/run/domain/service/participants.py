"""How a participant's answer is read, and what Taktus says back in the thread (ADR-0155).

Pure. A participant outside the organisation answers a `human` step in the channel and thread
the step before it opened. The answer is read by rule: as the text itself, or — where the step
offers options — as the one option it names, as a whole word and case-blind. A reading is said
back and waits for the same account's `yes` (ADR-0008); a `no` withdraws it; any other text is
a new answer.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

YES = frozenset({"yes", "ja", "y", "confirm", "confirmed", "ok", "okay"})
"""The words that confirm a reading, alone in the message once trimmed of punctuation."""
NO = frozenset({"no", "nein", "n"})
"""The words that withdraw it."""

READ = "read"
UNREAD = "unread"
"""The outcomes of `step.answer_read`: a reading said back, or an answer that named no option
or several, which the participant is asked again."""
WITHDRAWN = "withdrawn"
"""A reading the participant withdrew with a `no`."""
OUTCOME = "participant"
"""The outcome of `step.awaiting` of a step that waits for a participant."""
ANSWER_READ = "step.answer_read"


@dataclass(frozen=True)
class Reading:
    """What an answer was read as: the text the participant wrote, and the option it names
    where the step offers options."""

    answer: str
    option: str | None


type Said = Literal["answer", "yes", "no"]


REPLY_SUBJECT = re.compile(r"^\s*(re|aw|antw|fw|fwd|wg)\s*:", re.IGNORECASE)
"""A line a mail client opens a reply's subject with."""


def body_of(text: str) -> str:
    """What the participant wrote: without a reply's subject line, which a mail channel puts
    first, and without the quoted lines of what they answered."""
    lines = text.strip().splitlines()
    while lines and (not lines[0].strip() or REPLY_SUBJECT.match(lines[0])):
        lines = lines[1:]
    kept = [line for line in lines if not line.lstrip().startswith(">")]
    return "\n".join(kept).strip()


def said(text: str) -> Said:
    """Whether a message confirms, withdraws, or answers anew: by its first line, alone."""
    body = body_of(text)
    first = body.splitlines()[0] if body else ""
    word = re.sub(r"[\s.!,;:]+", " ", first).strip().casefold()
    if word in YES:
        return "yes"
    if word in NO:
        return "no"
    return "answer"


def read(text: str, options: tuple[str, ...]) -> Reading | None:
    """The reading of an answer, or None where the step offers options and the text names none
    of them, or more than one."""
    answer = body_of(text)
    if not options:
        return Reading(answer=answer, option=None) if answer else None
    named = [
        option
        for option in options
        if re.search(rf"(?<!\w){re.escape(option)}(?!\w)", answer, flags=re.IGNORECASE)
    ]
    if len(named) != 1:
        return None
    return Reading(answer=answer, option=named[0])


def account_digest(channel: str, account: str) -> str:
    """The account, as the block keeps it: a digest, never the account."""
    return "sha256:" + hashlib.sha256(f"{channel}\n{account}".encode()).hexdigest()


def reflected(reading: Reading) -> str:
    """The reading said back, asking for a confirmation."""
    what = f"“{reading.option}”" if reading.option is not None else f"“{reading.answer}”"
    return f"I read your answer as {what}. Reply yes to confirm, or answer again."


def asked_back(options: tuple[str, ...]) -> str:
    """An answer that named no option, or several: the options, asked again."""
    named = ", ".join(f"“{option}”" for option in options)
    return f"I could not read your answer as exactly one of {named}. Please answer with one."


def withdrawn() -> str:
    return "Understood, nothing is recorded. Please answer again."


def recorded() -> str:
    return "Thank you, your answer is recorded."


def labelled(text: str, label: str | None) -> str:
    """The reply with the tenant's label as a paragraph of its own, where it set one."""
    return text if not label else f"{text}\n\n{label}"
