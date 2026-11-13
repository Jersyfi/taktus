"""A chain of processes across domains, and what passes at each of its boundaries (UC-15.4,
ADR-0274).

A chain links process versions in order. At every boundary between two links it declares the
handover: each item the receiving process is given, as one of its inputs, the step of the
sending process whose result it is, the part of that result, and the clause of the chain that
requires it. Each link stays a process with its own version, owner and autonomy level.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.components.process.domain.model.process import Escalation
from taktus.shared.v1 import StepId, Value


class ChainRefused(Exception):
    """What a person asked of a chain run does not fit the state it is in (ADR-0302 §3)."""


class Item(Value):
    """One thing handed over at a boundary."""

    input: str = Field(min_length=1)
    """The input of the receiving process it fills."""
    step: StepId
    """The step of the sending process whose result it is."""
    select: str | None = Field(default=None, min_length=1)
    """The dotted path to the part of the result; None hands over the whole result."""
    clause: str = Field(min_length=1)
    """Why the chain requires it, in words: what the record of the handover names."""


class Link(Value):
    process_version: str = Field(pattern=r"^[a-z][a-z0-9-]*@[A-Za-z0-9][A-Za-z0-9._-]*$")
    handover: tuple[Item, ...] = ()
    """What passes from the link before to this one; empty for the first link."""


class ChainObjectives(Value):
    """The service level the chain as a whole promises, beside those of its links (UC-15.4,
    ADR-0302): how long one run of the chain may take, from its first link's start to its last
    link's end, and the least share of its ended runs that finish."""

    latency: timedelta | None = None
    completion: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def _something(self) -> ChainObjectives:
        if self.latency is None and self.completion is None:
            raise ValueError("a chain's `slo` names a `latency`, a `completion`, or both")
        if self.latency is not None and self.latency <= timedelta(0):
            raise ValueError("a chain's `slo.latency` is a time longer than nothing")
        return self


class Chain(Value):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    links: tuple[Link, ...] = Field(min_length=2)
    slo: ChainObjectives | None = None
    """The chain's own objectives; None: it promises none beyond its links'."""
    escalation: Escalation | None = None
    """Who a halted handover reaches, by which path, and how soon; None: the role `owner`, in
    the owner-facing channel."""

    @model_validator(mode="after")
    def _linked_once(self) -> Chain:
        refs = [link.process_version for link in self.links]
        if len(set(refs)) != len(refs):
            raise ValueError("a chain links each process version once")
        if self.links[0].handover:
            raise ValueError("the first link of a chain is handed nothing")
        if any(not link.handover for link in self.links[1:]):
            raise ValueError("every link after the first declares what is handed over to it")
        return self


class DeclaredChain(Value):
    """A chain as the tenant declared it (ADR-0301). A new declaration replaces it; a run keeps
    the chain it started with. Who declared it is the ledger entry's actor."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    chain: Chain
    declared_at: datetime

    @model_validator(mode="after")
    def _keyed(self) -> DeclaredChain:
        if self.id != self.chain.id:
            raise ValueError("a declared chain is kept under its own identifier")
        return self


class ChainState(StrEnum):
    RUNNING = "running"
    """A link runs."""
    WAITING = "waiting"
    """A link did not finish: it waits for a person, at an anchor, or was escalated. The chain
    goes on by itself once the link finished (ADR-0301 §3)."""
    HALTED = "halted"
    """A handover lacked a declared item: nothing passed, and a person decides (ADR-0302)."""
    FINISHED = "finished"
    STOPPED = "stopped"
    """A person stopped it, or a link ended without finishing and cannot go on."""


ENDED = frozenset({ChainState.FINISHED, ChainState.STOPPED})


class ChainRun(Value):
    """One run of a chain (ADR-0301): the chain it started with, the link it stands at, the run
    of every link that started and the digest of every handover recorded."""

    id: str = Field(min_length=1)
    chain: Chain
    state: ChainState
    started_at: datetime
    updated_at: datetime
    link: int = Field(default=0, ge=0)
    """The index of the link the chain stands at, counted from zero."""
    runs: tuple[str, ...] = ()
    """The run of every link that started, in order."""
    handovers: tuple[str, ...] = ()
    """The digest of every handover's document, in order."""
    reason: str | None = None
    """Why the chain stands where it does, in words, while it is not running or finished."""
    missing: tuple[str, ...] = ()
    """The inputs a halted handover lacked."""
    ended_at: datetime | None = None
    measured: str | None = None
    """The outcome its objectives were measured with once it ended: `met` or `missed_…`."""

    @property
    def ended(self) -> bool:
        return self.state in ENDED
