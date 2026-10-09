"""A product finding: what an instance met that the product lacks, and every time it met it
(UC-6.12, ADR-0046).

A *lack* is a block whose recorded cause says that no configured adapter offers what a step
needed: no worker for its capabilities, no connector for its capability, or no such operation on
the connector. The lack is the cause and what was lacking, and nothing else. Every block for the
same lack is one *occurrence* of it: the run and the step it held up, when it began, and — once
it ended — how long the step waited.

Every field is an identifier, a time, a duration or a count, each held to a pattern, so that no
text of a project, no personal datum and no secret value can pass into a finding (ADR-0006).
There is no field for a person, and a value of these types is closed (principle 14).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import Field

from taktus.shared.v1 import StepId, Value

type LackCause = Literal["no_worker", "no_connector", "operation_unsupported"]

LACK_CAUSES: frozenset[str] = frozenset({"no_worker", "no_connector", "operation_unsupported"})
"""The cause tokens of the blocked-time accounts that are a lack of the product (ADR-0046). The
run books them; a test holds the two lists equal."""

LACKING_PATTERN = r"^[a-z][a-z0-9_.-]*(,[a-z][a-z0-9_.-]*)*$"
"""What was lacking: a capability, several comma-separated, or an operation."""
RUN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
OCCURRENCE_PATTERN = r"^[0-9a-f]{16}$"


def short(text: str) -> str:
    """Sixteen hex digits of the SHA-256 of a text: an identity derived, never stored."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Blocked(Value):
    """A block as the blocked-time accounts record it, as far as a finding reads it: its cause,
    the run and the step it held up, when it began, and how long it lasted once it ended. Read
    from the run's accounts (ADR-0043) and from nothing else."""

    cause: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    run_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    since: datetime
    seconds: float | None = Field(default=None, ge=0)
    lacking: str | None = None


class Lack(Value):
    cause: LackCause
    lacking: str = Field(pattern=LACKING_PATTERN, max_length=200)

    @property
    def key(self) -> str:
        """The lack's identity, the same on every instance: what its finding is found by."""
        return short(f"{self.cause}:{self.lacking}")


class Occurrence(Value):
    """One block for a lack. `seconds` is set once the block ended."""

    run_id: str = Field(pattern=RUN_PATTERN, max_length=128)
    step_id: StepId
    since: datetime
    seconds: float | None = Field(default=None, ge=0)

    @property
    def id(self) -> str:
        """The occurrence's identity: the run, the step and when the block began."""
        return short(f"{self.run_id}|{self.step_id}|{self.since.isoformat()}")

    @property
    def ended(self) -> bool:
        return self.seconds is not None


class Finding(Value):
    """One lack, and every occurrence of it the instance knows, oldest first."""

    lack: Lack
    occurrences: tuple[Occurrence, ...] = Field(min_length=1)

    @property
    def waited(self) -> float:
        """The waiting of every occurrence that ended, summed."""
        return sum(o.seconds or 0.0 for o in self.occurrences)


class Reported(Value):
    """What a channel already holds of one occurrence: reported while its block lasted (`met`)
    or once it ended (`ended`), with the waiting reported then."""

    lack: str = Field(pattern=OCCURRENCE_PATTERN)
    occurrence: str = Field(pattern=OCCURRENCE_PATTERN)
    state: Literal["met", "ended"]
    seconds: float | None = Field(default=None, ge=0)
