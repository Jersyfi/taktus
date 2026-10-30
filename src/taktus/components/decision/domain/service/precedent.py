"""When the register shows a consistent pattern, and which requests a rule may ever answer
(ADR-0161, UC-7.10). A rule, by count — no model reads the register.

**Which requests a rule may answer.** Only a request raised by an anchor of the tenant's own
configuration of the class `strategic`. The tenant may reduce its strategic class (ADR-0008),
and a rule a person accepts is such a reduction, for one kind of request. Every other request
keeps its act with a person whatever the tenant configures, and no rule is ever proposed for it:

- the classes `legal` and `correction`, which can never be emptied (ADR-0008, ADR-0022), and
  the frame's own anchors, which are of the class `legal` (ADR-0130, ADR-0142);
- a step's own `ask`, which no tenant configuration removes (ADR-0088): it names no anchor;
- a check put to a person — an approval above a threshold, a sample (ADR-0152), class
  `domain`: a rule over it would count a value no one looked at;
- a proposal to change a process — a move to another method, its rollback, a rule itself
  (ADR-0084, ADR-0114), class `conceptual` or no anchor.

**What counts as consistent.** The `PRECEDENTS` most recent decisions of one kind, all decided
after the last proposal of that kind was decided, chose the same option, none of them with
modifications and none of them answered by a rule. One decision that chose otherwise, or carried
a modification, breaks the pattern until `PRECEDENTS` more agree again.

Pure: register entries in, a pattern or nothing out.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from taktus.components.decision.domain.model.request import RegisterEntry
from taktus.components.decision.domain.model.rule import RULE_ACTOR_PREFIX, Kind
from taktus.shared.v1 import DecisionClass, Value

PRECEDENTS = 5
"""How many decisions in a row of one kind, answered the same way, make a pattern."""


def refusal(class_: DecisionClass, anchor: str | None) -> str | None:
    """Why no rule may answer a request of this class and anchor; None when one may."""
    if class_ in (DecisionClass.LEGAL, DecisionClass.CORRECTION):
        return f"an anchor of the class {class_} keeps its act with a person at every level"
    if anchor is None:
        return (
            "a request no anchor of the tenant raised — a step's own ask, a check, a proposal "
            "to change a process — is never answered by a rule"
        )
    if class_ is not DecisionClass.STRATEGIC:
        return f"a request of the class {class_} is never answered by a rule"
    return None


def by_rule(entry: RegisterEntry) -> bool:
    return entry.decided_by.startswith(RULE_ACTOR_PREFIX)


class Pattern(Value):
    kind: Kind
    option: str
    proposal: str
    decider: str
    precedents: tuple[RegisterEntry, ...]


def pattern(
    kind: Kind, entries: Sequence[RegisterEntry], *, since: datetime | None = None
) -> Pattern | None:
    """The pattern the entries of one kind show, or None. `entries` are of the kind, in the order
    they were decided; `since` is when the last proposal of the kind was decided, if one was."""
    considered = [e for e in entries if since is None or e.decided_at > since]
    recent = considered[-PRECEDENTS:]
    if len(recent) < PRECEDENTS:
        return None
    first = recent[0]
    if refusal(first.class_, first.anchor) is not None:
        return None
    for entry in recent:
        if by_rule(entry) or entry.modifications is not None:
            return None
        if entry.option != first.option or entry.decider != first.decider:
            return None
    return Pattern(
        kind=kind,
        option=first.option,
        proposal=recent[-1].proposal,
        decider=first.decider,
        precedents=tuple(recent),
    )
