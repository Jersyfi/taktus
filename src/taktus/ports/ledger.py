"""The ledger as the core sees it: facts go in, chained entries come out.

A fact is what happened, as identifiers and measured quantities — a state change of a run, a
step admitted or finished, an assignment rejected. It carries no text beyond tokens: no reason,
no message, no payload, so that nothing personal and no secret can reach the chain (ADR-0006).
The ledger component turns a fact into an entry with sequence, time, and the hash link.

There is one chain per tenant (ADR-0020), so every call names the tenant. Recording happens
inside the caller's unit of work: the entry and the state change it describes are one
transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

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


class Verification(Value):
    """The result of walking the whole chain."""

    entries: int
    intact: bool
    findings: tuple[str, ...] = ()


class Ledger(Protocol):
    async def record(self, tenant: Tenant, fact: Fact) -> LedgerEntry: ...

    async def entries(self, tenant: Tenant, run_id: str | None = None) -> Sequence[LedgerEntry]:
        """The tenant's chain in order, or only the entries that reference one run."""
        ...

    async def verify(self, tenant: Tenant) -> Verification:
        """Walk the tenant's chain from the first entry: sequence gapless, every link matches,
        every hash recomputes. Any alteration of any entry is a finding."""
        ...
