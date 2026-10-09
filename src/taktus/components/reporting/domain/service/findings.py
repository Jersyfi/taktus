"""Which blocks are product findings, and what a channel still lacks of them (UC-6.12, ADR-0046).

**The rule.** A block is a product finding when its recorded cause is a lack of the product —
`no_worker`, `no_connector`, `operation_unsupported` — and it names what was lacking. Nothing
else decides: no model, no estimate, no reading of a reason in words (UC-6.12 §2). Every other
block, and every other friction, a person raises by hand from the run.

**One finding per lack.** Every block for the same lack is one occurrence of the same finding;
the finding is the lack and its occurrences, oldest first.

**What is still to send.** A channel holds what it was told of each occurrence: that it was met,
or that it ended and how long it waited. An occurrence it has not heard of is sent; one it heard
of while it lasted is sent again once it ended, with its waiting; one it heard of as ended is
never sent again. So a finding is sent once, and every report after it adds to it.

Pure: blocks and reports in, findings and what to send out.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import ValidationError

from taktus.components.reporting.domain.model.finding import (
    LACK_CAUSES,
    Blocked,
    Finding,
    Lack,
    Occurrence,
    Reported,
)

type State = Literal["met", "ended"]


def lack_of(block: Blocked) -> Lack | None:
    """The lack a block was for, or None when its cause is not a lack of the product. A block
    whose record does not name what was lacking as an identifier is no finding: nothing that is
    not an identifier is ever sent."""
    if block.cause not in LACK_CAUSES or block.lacking is None:
        return None
    try:
        return Lack.model_validate({"cause": block.cause, "lacking": block.lacking})
    except ValidationError:
        return None


def occurrence_of(block: Blocked) -> Occurrence | None:
    try:
        return Occurrence(
            run_id=block.run_id, step_id=block.step_id, since=block.since, seconds=block.seconds
        )
    except ValidationError:
        return None


def findings(blocks: Iterable[Blocked]) -> tuple[Finding, ...]:
    """Every lack among the blocks, each with its occurrences oldest first; the findings in the
    order their first occurrence was met. A block that ended and the same block still open — a
    record read while the step run was not yet cleared — are one occurrence, the ended one."""
    lacks: dict[str, Lack] = {}
    seen: dict[str, dict[str, Occurrence]] = defaultdict(dict)
    for block in blocks:
        lack = lack_of(block)
        occurrence = occurrence_of(block)
        if lack is None or occurrence is None:
            continue
        lacks.setdefault(lack.key, lack)
        known = seen[lack.key].get(occurrence.id)
        if known is None or (occurrence.ended and not known.ended):
            seen[lack.key][occurrence.id] = occurrence
    result = [
        Finding(
            lack=lacks[key],
            occurrences=tuple(sorted(found.values(), key=lambda o: (o.since, o.id))),
        )
        for key, found in seen.items()
    ]
    return tuple(sorted(result, key=lambda f: (f.occurrences[0].since, f.lack.key)))


def to_send(
    finding: Finding, reported: Mapping[str, Reported]
) -> tuple[tuple[Occurrence, State], ...]:
    """What the channel has not heard yet of the finding, oldest first: each occurrence with the
    state to report. `reported` is what the channel holds, by occurrence."""
    sends: list[tuple[Occurrence, State]] = []
    for occurrence in finding.occurrences:
        state: State = "ended" if occurrence.ended else "met"
        known = reported.get(occurrence.id)
        if known is None or (known.state == "met" and state == "ended"):
            sends.append((occurrence, state))
    return tuple(sends)
