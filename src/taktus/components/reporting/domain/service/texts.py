"""A product finding in words: the issue it opens and what each later report adds (UC-6.12).

The issue's body has the shape its operator configured (`form`, `TAKTUS_FINDINGS_FORM`): a
text with fields the finding fills — what was tried, what was lacking, the cause, where in the
product it lies, the run and the step. Without one it has the product's own plain shape
(`PLAIN`). The shape of one repository's backlog is that repository's configuration, never the
product's default (ADR-0092). Below the body, after a horizontal rule, the occurrences follow.
What a later occurrence adds is a comment on the same issue.

Every text is built from fixed sentences — the product's or the operator's form — and the
finding's identifiers, times, durations and counts, and from nothing else (ADR-0006). Each
carries a *mark*, an HTML comment that is not shown, stating the lack, the occurrence, its
state and the waiting reported. The marks are how a channel knows what it already holds,
without any memory on the instance (`reported`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC
from string import Template

from taktus.components.reporting.domain.model.finding import (
    Finding,
    Lack,
    Occurrence,
    Reported,
)
from taktus.components.reporting.domain.service.findings import State

MARK = "taktus-finding"
"""The word every mark begins with: what a channel searches for to find the findings it holds."""

_MARK = re.compile(
    r"<!-- taktus-finding lack=(?P<lack>[0-9a-f]{16}) occurrence=(?P<occurrence>[0-9a-f]{16}) "
    r"state=(?P<state>met|ended) seconds=(?P<seconds>-|[0-9]+(?:\.[0-9]+)?) -->"
)

_TITLES = {
    "no_worker": "no worker offers {lacking}",
    "no_connector": "no connector serves {lacking}",
    "operation_unsupported": "no connector offers the operation {lacking}",
}
_TRIED = {
    "no_worker": "A step needed a worker that offers `{lacking}`. No configured worker offers it.",
    "no_connector": "A step called the capability `{lacking}`. No configured connector serves it.",
    "operation_unsupported": (
        "A step called the operation `{lacking}`. The connector configured for its capability "
        "does not offer it."
    ),
}
_AREA = {
    "no_worker": "workers",
    "no_connector": "adapters",
    "operation_unsupported": "adapters",
}

FIELDS = ("tried", "lacking", "cause", "area", "run", "step")
"""What a form may name, each as `$field`: the sentence of what the step tried, the identifier
of what was lacking, the block's cause, where in the product it lies (`workers` or `adapters`),
and the run and step of the first occurrence. `$$` is a dollar sign."""

PLAIN = """An instance of Taktus met something the product lacks. $tried The step failed for it, \
and its run waited until the step could start again.

What would resolve it: the product offers `$lacking` among its $area, through an adapter or an \
operation of one it has, or says why it does not.

Where it was met: run `$run`, step `$step`, cause `$cause`, as the blocked-time accounts of the \
instance record it (UC-6.12)."""
"""The body of a finding where its operator configured no form: the product's own shape, which
assumes no repository's backlog."""


def form(text: str) -> str:
    """A form, validated: a text that names only the fields a finding fills. A form that names
    another, or writes a lone `$`, is a `ValueError` naming it."""
    template = Template(text)
    if not template.is_valid():
        raise ValueError("a form writes `$` only before a field's name; `$$` is a dollar sign")
    unknown = sorted(set(template.get_identifiers()) - set(FIELDS))
    if unknown:
        raise ValueError(f"a form names {', '.join(unknown)}; it may name only {', '.join(FIELDS)}")
    if not text.strip():
        raise ValueError("a form is empty")
    return text


def mark(lack: Lack, occurrence: Occurrence, state: State) -> str:
    seconds = "-" if occurrence.seconds is None else f"{occurrence.seconds:.0f}"
    return (
        f"<!-- {MARK} lack={lack.key} occurrence={occurrence.id} state={state} "
        f"seconds={seconds} -->"
    )


def reported(texts: Iterable[str]) -> tuple[Reported, ...]:
    """Every mark in the texts, in their order: what a channel holds."""
    found: list[Reported] = []
    for text in texts:
        for match in _MARK.finditer(text):
            seconds = match["seconds"]
            found.append(
                Reported(
                    lack=match["lack"],
                    occurrence=match["occurrence"],
                    state="met" if match["state"] == "met" else "ended",
                    seconds=None if seconds == "-" else float(seconds),
                )
            )
    return tuple(found)


def latest(marks: Iterable[Reported]) -> dict[str, Reported]:
    """What is known of each occurrence: its `ended` report where there is one, otherwise its
    `met` report."""
    known: dict[str, Reported] = {}
    for one in marks:
        before = known.get(one.occurrence)
        if before is None or before.state == "met":
            known[one.occurrence] = one
    return known


def title(lack: Lack) -> str:
    return "Product finding: " + _TITLES[lack.cause].format(lacking=lack.lacking)


def _seconds(seconds: float) -> str:
    return f"{seconds:.0f} s"


def _at(occurrence: Occurrence) -> str:
    return occurrence.since.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _occurrence(lack: Lack, occurrence: Occurrence, number: int, state: State) -> str:
    where = f"run `{occurrence.run_id}`, step `{occurrence.step_id}`, cause `{lack.cause}`"
    if state == "met":
        return f"Occurrence {number}: {where}, blocked since {_at(occurrence)}, still waiting."
    return (
        f"Occurrence {number}: {where}, blocked since {_at(occurrence)}, "
        f"waited {_seconds(occurrence.seconds or 0.0)}."
    )


def _in_all(known: Mapping[str, Reported]) -> str:
    ended = [r for r in known.values() if r.state == "ended"]
    open_ = len(known) - len(ended)
    waited = sum(r.seconds or 0.0 for r in ended)
    text = (
        f"In all: {len(known)} occurrence{'s' if len(known) != 1 else ''}, "
        f"{_seconds(waited)} waited over the {len(ended)} that ended"
    )
    return text + (f", {open_} still waiting." if open_ else ".")


def opening(lack: Lack, occurrence: Occurrence, state: State, shape: str | None = None) -> str:
    """The body of the issue a finding opens with its first occurrence: `shape`, the form its
    operator configured, filled — or the product's `PLAIN` — then the occurrence below a
    rule."""
    body = Template(PLAIN if shape is None else shape).substitute(
        tried=_TRIED[lack.cause].format(lacking=lack.lacking),
        lacking=lack.lacking,
        cause=lack.cause,
        area=_AREA[lack.cause],
        run=occurrence.run_id,
        step=occurrence.step_id,
    )
    lines = [
        body.rstrip(),
        "",
        "---",
        "",
        "Raised by an instance of Taktus from its blocked-time accounts (UC-6.12, ADR-0046).",
        "",
        _occurrence(lack, occurrence, 1, state),
        _in_all({occurrence.id: _as_reported(lack, occurrence, state)}),
        "",
        mark(lack, occurrence, state),
    ]
    return "\n".join(lines)


def addition(
    lack: Lack, occurrence: Occurrence, state: State, known: Mapping[str, Reported]
) -> str:
    """What a later report adds to the finding's issue: a new occurrence, or the end of one that
    was reported while it lasted. `known` is what the channel holds, before this report."""
    after = dict(known)
    after[occurrence.id] = _as_reported(lack, occurrence, state)
    order = list(known)
    number = order.index(occurrence.id) + 1 if occurrence.id in known else len(order) + 1
    if occurrence.id in known:
        head = f"The block of occurrence {number} ended."
    else:
        head = "The same lack was met again."
    lines = [head, "", _occurrence(lack, occurrence, number, state), _in_all(after)]
    return "\n".join([*lines, "", mark(lack, occurrence, state)])


def _as_reported(lack: Lack, occurrence: Occurrence, state: State) -> Reported:
    return Reported(
        lack=lack.key, occurrence=occurrence.id, state=state, seconds=occurrence.seconds
    )


def shown(finding: Finding, shape: str | None = None) -> str:
    """The finding as its operator reads it on the instance, to send by hand where sending is
    not enabled: the issue's title and body for the first occurrence, then one line for each
    other occurrence."""
    first, *others = finding.occurrences
    lines = [
        title(finding.lack),
        "",
        opening(finding.lack, first, "ended" if first.ended else "met", shape),
    ]
    for number, occurrence in enumerate(others, start=2):
        lines.append(
            _occurrence(finding.lack, occurrence, number, "ended" if occurrence.ended else "met")
        )
    if others:
        known = {
            o.id: _as_reported(finding.lack, o, "ended" if o.ended else "met")
            for o in finding.occurrences
        }
        lines.append(_in_all(known))
    return "\n".join(lines)
