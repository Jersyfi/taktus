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
by value (ADR-0015, protective rule; principle 14). Who answered which wait is answered by the
ledger entry of the answer, and only the person who answered reads it joined to the block
(`application/query/blocked_time.py`).

Pure: records and entries in, documents and sums out.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

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

    @property
    def process(self) -> str:
        return process_of(self.process_version)


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


class BlockedSum(Value):
    """The blocked time of one account, in one process, in one period. No person is a key."""

    account: Account
    process: str = Field(min_length=1)
    period: str = Field(min_length=1)
    seconds: float = Field(ge=0)
    """How long work stood still: the blocks' durations added up."""
    blocks: int = Field(ge=1)
    runs_held_up: int = Field(ge=1)
    steps_held_up: int = Field(ge=1)
    runs: int = Field(ge=1)
    """The runs of the process active in the period: every run with an entry in it."""
    share: float = Field(ge=0, le=1)
    """The share of the work blocked: runs held up by this account, of the runs active."""


def sums(
    blocks: Iterable[Block],
    active: Mapping[tuple[str, str], frozenset[str]],
    period: Period,
) -> tuple[BlockedSum, ...]:
    """Blocked time per account, per process and per period. A block falls in the period it
    ended in. `active` names, per process and period, the runs with an entry in it; every run
    a block held up has its record there, so the share never exceeds one. The order is by
    account, process and period, never by a figure."""
    seconds: dict[tuple[Account, str, str], float] = defaultdict(float)
    count: dict[tuple[Account, str, str], int] = defaultdict(int)
    runs: dict[tuple[Account, str, str], set[str]] = defaultdict(set)
    steps: dict[tuple[Account, str, str], set[tuple[str, str]]] = defaultdict(set)
    for block in blocks:
        key = (block.account, block.process, period_of(block.until, period))
        seconds[key] += block.seconds
        count[key] += 1
        runs[key].add(block.run_id)
        steps[key].add((block.run_id, block.step_id))
    result: list[BlockedSum] = []
    for key in sorted(seconds):
        account, process, at = key
        active_runs = len(active.get((process, at), frozenset()) | runs[key])
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
