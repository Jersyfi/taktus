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
import re
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from taktus.shared.v1 import StepId, Value

type LackCause = Literal["no_worker", "no_connector", "operation_unsupported"]

LACK_CAUSES: frozenset[str] = frozenset({"no_worker", "no_connector", "operation_unsupported"})
"""The cause tokens of the blocked-time accounts that are a lack of the product (ADR-0046). The
run books them; a test holds the two lists equal."""

LACKING_PATTERN = r"^[a-z][a-z0-9_.-]*(,[a-z][a-z0-9_.-]*)*$"
"""What was lacking: a capability, several comma-separated, or an operation."""
RUN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
OCCURRENCE_PATTERN = r"^[0-9a-f]{16}$"
SOURCE_PATTERN = r"^src_[0-9a-f]{20}$"
"""The sender of a finding: one tenant of one instance, by an identifier drawn at random on that
instance (ADR-0112 §3). It names no person, no operator and no tenant."""


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
    """One block for a lack. `seconds` is set once the block ended. `source` is the sender it is
    sent from; None on the instance, before it is made fit to leave (ADR-0112)."""

    run_id: str = Field(pattern=RUN_PATTERN, max_length=128)
    step_id: StepId
    since: datetime
    seconds: float | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, pattern=SOURCE_PATTERN)

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
    source: str | None = Field(default=None, pattern=SOURCE_PATTERN)
    """The sender that reported it; None for a mark written before senders were named."""


# --- what the release ships, and what a lack is (ADR-0118) -------------------------------------

type LackKind = Literal["product", "configuration", "own"]
"""A *product candidate*: nothing the release ships offers what was lacking. *Local:
configuration*: an adapter the release ships offers it, and the instance did not configure it.
*Local: own development*: it lies in the project's own vocabulary — an adapter, a process or a
bundle the project brought."""

type FindingsLevel = Literal["off", "review", "automatic"]
"""How a product candidate leaves an instance: not at all, the default; once a person said yes
to the text that would leave; or on its own, where the rule raised it."""

LEVELS: tuple[str, ...] = ("off", "review", "automatic")

ADAPTER_PATTERN = r"^[a-z][a-z0-9_-]*$"
NAME_PATTERN = r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$"


class ShippedAdapter(Value):
    """One adapter the release ships: its name, the capabilities it offers and, for a
    connector, the operations."""

    name: str = Field(pattern=ADAPTER_PATTERN)
    capabilities: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()


class Shipped(Value):
    """The workers and connectors a release ships, as the release carries them
    (`composition/shipped.json`)."""

    workers: tuple[ShippedAdapter, ...] = ()
    connectors: tuple[ShippedAdapter, ...] = ()

    @property
    def namespaces(self) -> frozenset[str]:
        """The first segment of every capability and operation shipped: the product's
        vocabulary."""
        return frozenset(
            name.split(".", 1)[0]
            for adapter in (*self.workers, *self.connectors)
            for name in (*adapter.capabilities, *adapter.operations)
        )


class Classified(Value):
    """What a lack is, by the rule over the release's list. `adapters` names the shipped adapters
    that would serve it, for a lack of configuration."""

    kind: LackKind
    adapters: tuple[str, ...] = ()

    @property
    def local(self) -> bool:
        return self.kind != "product"


# --- what leaves for an intake (ADR-0118 §4) ---------------------------------------------------

PSEUDONYM_RUN = r"^r-[0-9a-f]{16}$"
PSEUDONYM_STEP = r"^s-[0-9a-f]{12}$"
TITLE_MAX = 200
BODY_MAX = 20000


class Submission(Value):
    """One finding's occurrence, or one report by hand, as a sender submits it to an intake:
    closed values for a finding, the person's checked text for a report. The intake composes
    the issue's text itself, so a sender cannot put words of its own into a finding."""

    source: str = Field(pattern=SOURCE_PATTERN)
    lack: Lack | None = None
    occurrence: Occurrence | None = None
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    body: str | None = Field(default=None, min_length=1, max_length=BODY_MAX)

    @model_validator(mode="after")
    def _one_of_two(self) -> Submission:
        finding = self.lack is not None and self.occurrence is not None
        report = self.title is not None and self.body is not None
        if finding == report or (finding and (self.title or self.body)):
            raise ValueError("a submission is a finding's occurrence or a report, never both")
        if report and (self.lack is not None or self.occurrence is not None):
            raise ValueError("a report carries no lack")
        if self.occurrence is not None:
            if self.occurrence.source != self.source:
                raise ValueError("an occurrence names the sender that submits it")
            if not re.fullmatch(PSEUDONYM_RUN, self.occurrence.run_id) or not re.fullmatch(
                PSEUDONYM_STEP, self.occurrence.step_id
            ):
                raise ValueError("an occurrence leaves by pseudonym")
        return self

    @property
    def is_report(self) -> bool:
        return self.title is not None
