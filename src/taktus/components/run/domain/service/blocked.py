"""Blocked-time accounts (ADR-0015 §1, ADR-0043): the record of a block, and its sums.

When a block ends, the engine writes its record: a document with the block's account and cause,
the run, the step and the process version it held up, when it began and ended, and how long it
lasted. The ledger entry `step.waited` names the document by digest, and carries the cause token
as its outcome. The record and the entry are what the sums are computed from, and nothing else.

The sums are per account, per process and per period. Each says how long work stood still, how
many blocks there were, how many runs and steps they held up, and the share of the runs active
in the period that were held up at all.

A person is in neither. A block on a person carries no name: the account `wait.human` holds the
time, and anyone reads it summed over every person, never per person and never in an order
by value (ADR-0015, protective rule; principle 14). A sum of `wait.human` that fewer than two
persons answered is withheld, count and all: summed over one person, it is that person's
number under the name of a process (ADR-0042, NTC-0168). Who answered which wait is answered by
the ledger entry of the answer, and only the person who answered reads it joined to the block
(`application/query/blocked_time.py`).

Pure: records and entries in, documents and sums out.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from taktus.components.run.domain.model.block import CAUSE_PATTERN, Account, OpenBlock
from taktus.shared.v1 import StepId, Value

type Period = Literal["day", "week", "month"]

RECORD_KIND = "step.waited"
"""The ledger entry that names the record of a block that ended."""

RECORD_FIELDS = (
    "account",
    "cause",
    "run_id",
    "step_id",
    "process_version",
    "since",
    "until",
    "seconds",
    "on",
    "role",
    "lacking",
)
"""What every record carries. A record may carry more about its cause — the worker asked, how
often — and the sums read none of it."""


class Block(Value):
    """A block that ended, as its record states it. There is no field for a person, and none can
    be added by a record: a value of this type is closed."""

    account: Account
    cause: str = Field(pattern=CAUSE_PATTERN)
    run_id: str = Field(min_length=1)
    step_id: StepId
    process_version: str = Field(min_length=1)
    since: datetime
    until: datetime
    seconds: float = Field(ge=0)
    on: StepId | None = None
    role: str | None = Field(default=None, min_length=1)
    """The role a wait on a person was addressed to, where it was addressed to one."""
    lacking: str | None = Field(default=None, min_length=1)
    """For a lack (ADR-0046): what no configured adapter offered."""

    @property
    def process(self) -> str:
        return process_of(self.process_version)


class Waiting(Value):
    """A block that has not ended, with the run and the step it holds up: what a step run
    carries while it waits, read where it is. It is in no sum (ADR-0043 §6); a reader that must
    know of a block before it ends reads it here (ADR-0046)."""

    account: Account
    cause: str = Field(pattern=CAUSE_PATTERN)
    run_id: str = Field(min_length=1)
    step_id: StepId
    process_version: str = Field(min_length=1)
    since: datetime
    on: StepId | None = None
    role: str | None = Field(default=None, min_length=1)
    lacking: str | None = Field(default=None, min_length=1)


def waiting(block: OpenBlock, *, run_id: str, step_id: StepId, process_version: str) -> Waiting:
    """The open block of one step run, with what it holds up."""
    return Waiting(
        account=block.account,
        cause=block.cause,
        run_id=run_id,
        step_id=step_id,
        process_version=process_version,
        since=block.since,
        on=block.on,
        role=block.role,
        lacking=block.lacking,
    )


def process_of(process_version: str) -> str:
    """The process a version belongs to: the part before `@` (`ProcessVersion.ref`)."""
    return process_version.split("@", 1)[0]


def record(
    block: OpenBlock,
    *,
    run_id: str,
    step_id: StepId,
    process_version: str,
    until: datetime,
    **more: Any,
) -> dict[str, Any]:
    """The record of a block that ended at `until`. `more` adds what the cause has to say, and
    never a person."""
    document: dict[str, Any] = {
        **more,
        "account": block.account,
        "cause": block.cause,
        "run_id": run_id,
        "step_id": step_id,
        "process_version": process_version,
        "since": block.since.isoformat(),
        "until": until.isoformat(),
        "seconds": max(0.0, (until - block.since).total_seconds()),
    }
    if block.on is not None:
        document["on"] = block.on
    if block.role is not None:
        document["role"] = block.role
    if block.lacking is not None:
        document["lacking"] = block.lacking
    return document


def parse(document: Mapping[str, Any]) -> Block:
    """The block a record states; what it carries beyond the common fields is left aside."""
    return Block.model_validate({k: document[k] for k in RECORD_FIELDS if k in document})


def period_of(at: datetime, period: Period) -> str:
    """The period a moment falls in: `2026-10-09`, `2026-W41`, `2026-10`."""
    if period == "day":
        return at.date().isoformat()
    if period == "week":
        year, week, _ = at.isocalendar()
        return f"{year}-W{week:02d}"
    return f"{at.year:04d}-{at.month:02d}"


MINIMUM_PERSONS = 2
"""A sum of waits on a person stands only over this many distinct persons who answered them. A
sum over one person is that person's response time under the name of a process: it is withheld,
count and all, as an aggregate of response times is (ADR-0042, NTC-0088, NTC-0168)."""

PERSON_ACCOUNT = "wait.human"
"""The account whose time is time a person took to answer."""


class BlockedSum(Value):
    """The blocked time of one account, in one process, in one period. No person is a key.

    A sum of `wait.human` that fewer than `MINIMUM_PERSONS` persons answered carries its key,
    the runs active and why it is withheld, and no figure of the wait."""

    account: Account
    process: str = Field(min_length=1)
    period: str = Field(min_length=1)
    seconds: float | None = Field(default=None, ge=0)
    """How long work stood still: the blocks' durations added up."""
    blocks: int | None = Field(default=None, ge=1)
    runs_held_up: int | None = Field(default=None, ge=1)
    steps_held_up: int | None = Field(default=None, ge=1)
    runs: int = Field(ge=1)
    """The runs of the process active in the period: every run with an entry in it."""
    share: float | None = Field(default=None, ge=0, le=1)
    """The share of the work blocked: runs held up by this account, of the runs active."""
    withheld: str | None = Field(default=None, min_length=1)
    """Why the figures are not shown, when they are not."""

    @model_validator(mode="after")
    def _figures_or_the_reason(self) -> BlockedSum:
        figures = (self.seconds, self.blocks, self.runs_held_up, self.steps_held_up, self.share)
        if self.withheld is None and any(f is None for f in figures):
            raise ValueError("a sum shown carries every figure")
        if self.withheld is not None and any(f is not None for f in figures):
            raise ValueError("a sum withheld carries no figure of the wait")
        return self


def sums(
    blocks: Iterable[tuple[Block, str | None]],
    active: Mapping[tuple[str, str], frozenset[str]],
    period: Period,
) -> tuple[BlockedSum, ...]:
    """Blocked time per account, per process and per period. Each block comes with the person
    who ended it by answering, or None where no person did; the person is counted, never
    kept. A block falls in the period it ended in. `active` names, per process and period, the
    runs with an entry in it; every run a block held up has its record there, so the share
    never exceeds one. The order is by account, process and period, never by a figure."""
    seconds: dict[tuple[Account, str, str], float] = defaultdict(float)
    count: dict[tuple[Account, str, str], int] = defaultdict(int)
    runs: dict[tuple[Account, str, str], set[str]] = defaultdict(set)
    steps: dict[tuple[Account, str, str], set[tuple[str, str]]] = defaultdict(set)
    persons: dict[tuple[Account, str, str], set[str]] = defaultdict(set)
    for block, person in blocks:
        key = (block.account, block.process, period_of(block.until, period))
        seconds[key] += block.seconds
        count[key] += 1
        runs[key].add(block.run_id)
        steps[key].add((block.run_id, block.step_id))
        if person is not None:
            persons[key].add(person)
    result: list[BlockedSum] = []
    for key in sorted(seconds):
        account, process, at = key
        active_runs = len(active.get((process, at), frozenset()) | runs[key])
        if account == PERSON_ACCOUNT and len(persons[key]) < MINIMUM_PERSONS:
            result.append(
                BlockedSum(
                    account=account,
                    process=process,
                    period=at,
                    runs=active_runs,
                    withheld=f"fewer than {MINIMUM_PERSONS} persons answered: the figure "
                    "would be one person's (ADR-0015)",
                )
            )
            continue
        result.append(
            BlockedSum(
                account=account,
                process=process,
                period=at,
                seconds=seconds[key],
                blocks=count[key],
                runs_held_up=len(runs[key]),
                steps_held_up=len(steps[key]),
                runs=active_runs,
                share=len(runs[key]) / active_runs,
            )
        )
    return tuple(result)
