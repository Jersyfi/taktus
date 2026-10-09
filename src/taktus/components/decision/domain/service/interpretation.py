"""How an answer is read, and the one message that reflects the reading back (ADR-0008,
governance.md §3.2). Pure.

**Never interpret silently, and never guess.** An answer is read by a rule: it names exactly one
of the request's options — as a letter standing alone ("B", "B, but later") or as "option B" in
any case — or no option can be read from it. Words around the letter are not interpreted: they
are kept with the decision as written, and the reflection says that Taktus does not act on
them. An answer that names no option, or more than one, is not read at all; the reflection asks
for one option and lists them. Nothing takes effect before the person confirms the reading.

The rule is the method `rule`: reproducible, and wrong only in a way the person sees in the
reflection before anything happens. A model that reads intent into free text could read more,
and would have to be confirmed all the same.
"""

from __future__ import annotations

import re

from taktus.shared.v1 import AnswerInterpreted, DecisionOption, DecisionRequest

_STANDING = re.compile(r"(?<![A-Za-z0-9])([A-Z])(?![A-Za-z0-9])")
_NAMED = re.compile(r"\boption\s+([a-z])\b", re.IGNORECASE)
_BARE = re.compile(r"^\s*(?:option\s+)?([A-Za-z])\s*[.!]?\s*$", re.IGNORECASE)


def interpret(text: str, options: tuple[DecisionOption, ...]) -> AnswerInterpreted | None:
    """The option the answer names, with the rest of the answer kept as written; None when
    the answer names no option or more than one."""
    ids = {o.id for o in options}
    named = {m.upper() for m in _NAMED.findall(text)} | set(_STANDING.findall(text))
    found = sorted(named & ids)
    if len(found) != 1:
        return None
    bare = _BARE.match(text)
    rest = None if bare is not None and bare.group(1).upper() == found[0] else text.strip()
    return AnswerInterpreted(option=found[0], modifications=rest or None)


def chosen(option: str) -> AnswerInterpreted:
    """An answer that chose an option by its identifier: read as exactly that option."""
    return AnswerInterpreted(option=option)


def reflect(request: DecisionRequest, reading: AnswerInterpreted | None) -> str:
    """The one message sent back for an answer."""
    if reading is None:
        listed = "; ".join(f"{o.id} — {o.proposal}" for o in request.options)
        return (
            "I could not read one option from your answer, so nothing changes. "
            f"Please answer with one of: {listed}"
        )
    option = next(o for o in request.options if o.id == reading.option)
    message = f"I read your answer as option {option.id}: {option.proposal}"
    if option.consequence:
        message += f" {option.consequence}"
    if reading.modifications:
        message += (
            f' What else you wrote — "{reading.modifications}" — is kept with the decision; '
            "Taktus does not act on it."
        )
    return message + " Confirm to apply this, or answer again."
