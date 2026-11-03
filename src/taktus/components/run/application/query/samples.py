"""The error rate of a sampling check, read from its samples (UC-4.13, the row *sampling*;
ADR-0152).

A sampling check puts a stated share of a step's results to a person of its role after the
fact; the run records each sample as `check.sampled`, naming the step, the check by its place
(`check_<n>`) and the decision request. The rate per check is read here: how many results were
sampled, how many a person judged, and how many of those were wrong. It names no person: the
verdict is the result's, not the decider's (principle 14).
"""

from __future__ import annotations

from dataclasses import dataclass

from taktus.components.run.domain.service.anchoring import WRONG
from taktus.components.run.ports import Decisions
from taktus.ports.ledger import Ledger
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import Value

SAMPLED = "check.sampled"


class SampleRate(Value):
    """One sampling check of one step of one process version, and what its samples found."""

    process_version: str
    step_id: str
    check: str
    """The check by its place in the step's declaration: `check_1`, `check_2`, …"""
    sampled: int
    judged: int
    wrong: int

    @property
    def rate(self) -> float | None:
        """Wrong results per judged one; None while none was judged."""
        return None if self.judged == 0 else self.wrong / self.judged


@dataclass(frozen=True)
class SampleRates:
    ledger: Ledger
    work: UnitOfWork
    decisions: Decisions

    async def of(self, tenant: Tenant, process_version: str | None = None) -> list[SampleRate]:
        """Every sampling check that sampled a result, in the order it first did."""
        async with self.work.transaction(tenant):
            entries = await self.ledger.of_kinds(tenant, (SAMPLED,))
        counted: dict[tuple[str, str, str], list[int]] = {}
        for entry in entries:
            refs = entry.refs
            if refs.process_version is None or refs.step_id is None or entry.outcome is None:
                continue
            if process_version is not None and refs.process_version != process_version:
                continue
            key = (refs.process_version, refs.step_id, entry.outcome)
            figures = counted.setdefault(key, [0, 0, 0])
            figures[0] += 1
            if refs.decision_request_id is None:
                continue
            verdict = await self.decisions.verdict(tenant, refs.decision_request_id)
            if verdict is None or not verdict.applied:
                continue
            figures[1] += 1
            if verdict.option == WRONG:
                figures[2] += 1
        return [
            SampleRate(
                process_version=version, step_id=step, check=check, sampled=s, judged=j, wrong=w
            )
            for (version, step, check), (s, j, w) in counted.items()
        ]
