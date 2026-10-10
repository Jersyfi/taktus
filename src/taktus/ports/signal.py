"""The signal that a tenant's ledger gained entries (ADR-0055 §2).

A signal wakes a reader; it is never a record. What a reader receives is read from the ledger,
so a lost signal delays a change and never loses one: a reader that hears nothing reads anyway,
at an interval. The signal carries the tenant and nothing else.

The default adapter is a notification of the database the ledger lives in. A cluster may supply
another, a message broker for example (ADR-0002, the event bus).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from taktus.ports.persistence import Tenant


class LedgerSignal(Protocol):
    def tenants(self) -> AsyncIterator[Tenant]:
        """Each tenant whose ledger gained entries, as the transaction that wrote them commits.
        It runs until it is cancelled. A connection lost underneath it is opened again; what
        was signalled in between is lost, and is the reason a reader reads at an interval as
        well."""
        ...
