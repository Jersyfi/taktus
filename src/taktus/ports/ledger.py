"""The ledger as the core sees it: facts go in, chained entries come out.

A fact is what happened, as identifiers and measured quantities — a state change of a run, a
step admitted or finished, an assignment rejected. It carries no text beyond tokens: no reason,
no message, no payload, so that nothing personal and no secret can reach the chain (ADR-0006).
The ledger component turns a fact into an entry with sequence, time, and the hash link.

There is one chain per tenant (ADR-0020), so every call names the tenant. Recording happens
inside the caller's unit of work: the entry and the state change it describes are one
transaction.

A read costs what it returns (ADR-0105). The entries of one run, or of some kinds, are read
without the rest of the chain. A value computed over the whole history — the calibration, the
activity of runs — is a `Projection`: it is stored with the sequence number of the last entry it
read, and a read brings it up to date from there. It is derived from the ledger alone and can be
rebuilt from it at any time.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import Field

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Consumption, Digest, LedgerEntry, LedgerRefs, Method, Value
from taktus.shared.v1.ledger_entry import KIND_PATTERN, OUTCOME_PATTERN
from taktus.shared.v1.step import MODEL_PATTERN


class Fact(Value):
    """A ledger entry before it is chained: everything but seq, ts, prev_hash and hash."""

    kind: str = Field(pattern=KIND_PATTERN)
    refs: LedgerRefs
    method: Method | None = None
    model: str | None = Field(default=None, pattern=MODEL_PATTERN)
    adapter: str | None = Field(default=None, min_length=1)
    consumption: Consumption | None = None
    outcome: str | None = Field(default=None, pattern=OUTCOME_PATTERN)
    content_digest: Digest | None = None
    rehearsal: Literal[True] | None = None
    """Set on every fact of a rehearsal run (ADR-0030); None on every other."""


class Verification(Value):
    """The result of walking the chain, from its checkpoint or from its first entry."""

    entries: int
    """How many entries the chain holds, up to the last one the walk reached."""
    intact: bool
    findings: tuple[str, ...] = ()
    checkpoint: int = Field(default=0, ge=0)
    """The sequence number the walk started after: the last verified checkpoint, or 0 for a
    walk from the first entry (ADR-0105 §6)."""


class Projection[S](Protocol):
    """A value computed from a tenant's ledger, entry by entry (ADR-0105). Folding every entry
    of its kinds, in sequence order, from `empty()` gives the value; folding the entries after
    a stored value's sequence number into it gives the same value. `dump` and `load` carry it
    to and from the store as a JSON document."""

    @property
    def name(self) -> str:
        """Stable while the rule is: a projection whose rule changes takes a new name, and is
        then rebuilt from the first entry."""
        ...

    @property
    def kinds(self) -> frozenset[str] | None:
        """The kinds of entry the projection reads; None for every kind."""
        ...

    def empty(self) -> S: ...

    def fold(self, state: S, entry: LedgerEntry) -> S: ...

    def dump(self, state: S) -> dict[str, Any]: ...

    def load(self, document: Mapping[str, Any]) -> S: ...


class Ledger(Protocol):
    async def record(self, tenant: Tenant, fact: Fact) -> LedgerEntry: ...

    async def entries(self, tenant: Tenant, run_id: str | None = None) -> Sequence[LedgerEntry]:
        """The tenant's chain in order, or only the entries that reference one run: those are
        read without reading the rest of the chain."""
        ...

    async def of_kinds(self, tenant: Tenant, kinds: Collection[str]) -> Sequence[LedgerEntry]:
        """The entries of these kinds, in sequence order, read without reading the others."""
        ...

    async def project[S](self, tenant: Tenant, projection: Projection[S]) -> S:
        """The projection's value at the newest entry: the stored value, brought up to date
        with the entries after the sequence number it records, and stored again."""
        ...

    async def rebuilt[S](self, tenant: Tenant, projection: Projection[S]) -> S:
        """The projection's value folded from the first entry, whatever is stored, and stored
        in place of what was: what the stored value must equal."""
        ...

    async def verify(self, tenant: Tenant, *, full: bool = False) -> Verification:
        """Walk the tenant's chain from its last verified checkpoint: sequence gapless, every
        link matches, every hash recomputes. Any alteration of an entry after the checkpoint
        is a finding. `full` walks from the first entry and trusts no checkpoint: any
        alteration of any entry is a finding (ADR-0105 §7)."""
        ...
