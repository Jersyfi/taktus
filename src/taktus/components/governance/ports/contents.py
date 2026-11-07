"""What the recorded results of a step hold, for the window of a result defect (UC-4.11,
ADR-0271 §4, §5).

The results are the run component's and their content the object store's; the composition
answers this port from both, and from the check that marked the defect."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Protocol

from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Provenance


class RecordedContents(Protocol):
    async def shapes(
        self, tenant: Tenant, series: Sequence[Provenance]
    ) -> Mapping[tuple[str, str], str]:
        """The shape of the content each record's step read, by run and step: what it read
        from a source, or the results of the steps it read. A record whose content cannot be
        read has none."""
        ...

    async def marked(
        self, tenant: Tenant, run_id: str, step_id: str, series: Sequence[Provenance]
    ) -> Collection[str]:
        """The runs of `series` whose result the check that marked this one suspect marks when
        it is run again over the recorded results, each against what was recorded before it.
        Empty where no check marked it, or where the check reads a source, which cannot be
        read as it was."""
        ...
