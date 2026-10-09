"""How long deciders take to answer, and who may read it (ADR-0015, principle 14). Pure.

A response time is the time from a request being raised to the answer that took effect. It is
measured, and it is exactly the number principle 14 forbids once it is used to assess a person.
So the rule lives here, in what the read returns, not in a policy beside it:

- **The decider reads their own**, each decision with its time.
- **Anyone else reads aggregates only**: by the role that decided, and by the department of
  the deciders — never by person, and never ranked.
- **An aggregate over fewer than `MINIMUM_DECIDERS` distinct deciders is withheld**: an average
  over one person is that person's number under another name.

Nothing in the result names a decider other than the reader.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from statistics import median

from pydantic import Field

from taktus.components.decision.domain.model.request import RegisterEntry
from taktus.shared.v1 import Value

MINIMUM_DECIDERS = 2


class Own(Value):
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    seconds: float = Field(ge=0)


class Aggregate(Value):
    group: str = Field(min_length=1)
    """The role, or the department."""
    decisions: int | None = Field(default=None, ge=0)
    """None when withheld: a count over one person is that person's too."""
    median_seconds: float | None = None
    """None when withheld."""
    withheld: str | None = None
    """Why the figure is not shown, when it is not."""


class ResponseTimes(Value):
    reader: str = Field(min_length=1)
    own: tuple[Own, ...] = ()
    by_role: tuple[Aggregate, ...] = ()
    by_department: tuple[Aggregate, ...] = ()


def seconds(entry: RegisterEntry) -> float:
    return max((entry.answered_at - entry.raised_at).total_seconds(), 0.0)


def read(
    reader: str,
    entries: Sequence[RegisterEntry],
    department_of: Callable[[str], str | None],
) -> ResponseTimes:
    """What `reader` may see of the response times in `entries`. `department_of` places a
    decider in a department; a decider it cannot place is counted in no department."""
    own = tuple(
        Own(request_id=e.request_id, run_id=e.run_id, seconds=seconds(e))
        for e in entries
        if e.decided_by == reader
    )
    return ResponseTimes(
        reader=reader,
        own=own,
        by_role=_aggregates(entries, lambda e: e.decider),
        by_department=_aggregates(entries, lambda e: department_of(e.decided_by)),
    )


def _aggregates(
    entries: Sequence[RegisterEntry], group_of: Callable[[RegisterEntry], str | None]
) -> tuple[Aggregate, ...]:
    groups: dict[str, list[RegisterEntry]] = {}
    for entry in entries:
        group = group_of(entry)
        if group is not None:
            groups.setdefault(group, []).append(entry)
    result = []
    for group, members in sorted(groups.items()):
        deciders = {m.decided_by for m in members}
        if len(deciders) < MINIMUM_DECIDERS:
            result.append(
                Aggregate(
                    group=group,
                    withheld=f"fewer than {MINIMUM_DECIDERS} deciders: the figure would be "
                    "one person's (ADR-0015)",
                )
            )
            continue
        result.append(
            Aggregate(
                group=group,
                decisions=len(members),
                median_seconds=median(seconds(m) for m in members),
            )
        )
    return tuple(result)
