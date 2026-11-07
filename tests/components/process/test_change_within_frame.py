"""Taktus changes a process within the frame its owner declares (UC-4.3, ADR-0255), over the
memory stores.

What is real: registration, the proposals, the rule that judges a change, the ledger. What is
proven: a change within the frame is a new version that records the observation that led to
it, the replaced version stays as it was, and rolling back makes it current again as a new
version; a version registration refuses becomes a proposal with the findings; a change the
frame does not list is a proposal; and each change that is always outside — raising autonomy,
changing a method kind, loosening exactness, narrowing an anchor, widening reach or
credentials — asked for as a change within a frame that lists every kind, is a proposal and
never a version.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock, FakeIdentifiers
from fakes.takeover import instructed

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.change_within_frame import (
    ChangeProcess,
    ChangeWithinFrame,
    Observation,
)
from taktus.components.process.application.service.proposals import Proposals
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import Process, ProcessVersion, Proposal
from taktus.components.process.domain.service.bundle import bundle_of

TENANT = "t"
OWNER = "idn_owner"
AT = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
CHANGED_INTERFACE = Observation(
    observed="interface",
    on="issues.items.list",
    said="the operation takes `status` where it took `state`",
)


def base() -> dict[str, Any]:
    return instructed(
        {
            "id": "triage",
            "version": "1",
            "name": "Triage",
            "autonomy": {"level": 2, "reason": "a test", "toward_next": "twenty clean runs"},
            "frame": {"changes": ["work", "step_added", "checks_added", "takeover"]},
            "steps": [
                {
                    "id": "read",
                    "method": "rule",
                    "reason": "a read by rule",
                    "rejected": [],
                    "exactness": "tolerant",
                    "work": {"operation": "issues.items.list", "input": {"state": "open"}},
                },
                {
                    "id": "count",
                    "method": "rule",
                    "reason": "a count by rule",
                    "rejected": [],
                    "exactness": "exact",
                    "checks": [
                        {"kind": "recomputation"},
                        {"kind": "approval", "threshold": 100, "role": "operations"},
                    ],
                    "depends_on": ["read"],
                    "work": {"rule": "constant", "value": 1},
                },
                {
                    "id": "review",
                    "method": "human",
                    "reason": "a person reviews the count",
                    "rejected": [],
                    "depends_on": ["count"],
                },
            ],
        }
    )


class World:
    def __init__(self) -> None:
        self.persistence = MemoryPersistence()
        self.clock = FakeClock(AT)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.processes = MemoryRepository(self.persistence, Process)
        self.proposals = MemoryRepository(self.persistence, Proposal)
        self.register = RegisterProcessVersionHandler(
            self.versions, self.persistence, self.processes, ledger=self.ledger, clock=self.clock
        )
        self.change = ChangeWithinFrame(
            versions=self.versions,
            processes=self.processes,
            work=self.persistence,
            register=self.register,
            proposals=Proposals(
                self.versions,
                self.processes,
                self.proposals,
                self.persistence,
                self.clock,
                FakeIdentifiers(),
            ),
            ledger=self.ledger,
        )

    async def registered(self, bundle: dict[str, Any] | None = None) -> World:
        await self.register.execute(
            RegisterProcessVersion(bundle or base(), tenant=TENANT, by=OWNER)
        )
        return self

    async def changed(self, bundle: dict[str, Any], reason: str = "the interface changed") -> Any:
        return await self.change.execute(
            ChangeProcess(TENANT, "triage", bundle, reason, CHANGED_INTERFACE)
        )

    async def active(self) -> str | None:
        async with self.persistence.transaction(TENANT):
            process = await self.processes.get(TENANT, "triage")
        return None if process is None else process.active_version

    async def stored(self, ref: str) -> ProcessVersion | None:
        async with self.persistence.transaction(TENANT):
            return await self.versions.get(TENANT, ref)

    async def kinds(self) -> list[str]:
        async with self.persistence.transaction(TENANT):
            return [
                f"{e.kind}:{e.outcome}"
                for e in await self.ledger.entries(TENANT)
                if e.kind.startswith("process.")
            ]


def changed(edit: Callable[[dict[str, Any]], None], version: str = "2") -> dict[str, Any]:
    bundle = copy.deepcopy(base())
    bundle["version"] = version
    edit(bundle)
    return bundle


def step(bundle: dict[str, Any], step_id: str) -> dict[str, Any]:
    (found,) = [s for s in bundle["steps"] if s["id"] == step_id]
    return found


def new_field(bundle: dict[str, Any]) -> None:
    step(bundle, "read")["work"]["input"] = {"status": "open"}


async def test_a_change_within_the_frame_is_a_version_that_records_what_led_to_it() -> None:
    w = await World().registered()
    outcome = await w.changed(changed(new_field))
    assert outcome.proposal is None and outcome.version is not None
    version = outcome.version
    assert (version.ref, version.author, version.reason) == (
        "triage@2",
        "taktus",
        "the interface changed",
    )
    assert version.change is not None
    assert (version.change.observed, version.change.on) == ("interface", "issues.items.list")
    assert version.change.said == CHANGED_INTERFACE.said
    assert version.change.predecessor == "triage@1"
    assert version.change.changes == ("step read: its work changed",)
    assert await w.active() == "2"
    predecessor = await w.stored("triage@1")
    assert predecessor is not None and predecessor.work["read"]["input"] == {"state": "open"}, (
        "the replaced version stays registered and unchanged"
    )
    assert "process.changed:within_frame" in await w.kinds()


async def test_rolling_back_makes_the_predecessor_current_again_as_a_new_version() -> None:
    w = await World().registered()
    await w.changed(changed(new_field))
    predecessor = await w.stored("triage@1")
    assert predecessor is not None
    restored = await w.register.execute(
        RegisterProcessVersion(
            bundle_of(predecessor, as_version="3", author=OWNER, reason="rolled back to 1"),
            tenant=TENANT,
            by=OWNER,
        )
    )
    assert await w.active() == "3"
    assert restored.work == predecessor.work and restored.change is None
    assert await w.stored("triage@2") is not None, "nothing is deleted"


async def test_a_version_registration_refuses_becomes_a_proposal_with_the_findings() -> None:
    """A step added within the frame, whose takeover instructions have no entry for it."""

    def added(bundle: dict[str, Any]) -> None:
        bundle["steps"].append(
            {
                "id": "label",
                "method": "rule",
                "reason": "a label by rule",
                "rejected": [],
                "exactness": "tolerant",
                "depends_on": ["read"],
                "work": {"rule": "constant", "value": "triaged"},
            }
        )

    w = await World().registered()
    outcome = await w.changed(changed(added))
    assert outcome.version is None and outcome.proposal is not None
    assert any("label" in finding for finding in outcome.proposal.findings)
    assert outcome.proposal.change is not None
    assert outcome.proposal.change.said == CHANGED_INTERFACE.said
    assert await w.active() == "1" and await w.stored("triage@2") is None
    assert "process.change_proposed:not_registered" in await w.kinds()


async def test_a_change_the_frame_does_not_list_is_a_proposal() -> None:
    no_frame = base()
    del no_frame["frame"]
    w = await World().registered(no_frame)
    bundle = changed(new_field)
    del bundle["frame"]
    outcome = await w.changed(bundle)
    assert outcome.version is None and outcome.proposal is not None
    assert outcome.proposal.findings == (
        "step read: its work changed: of the kind 'work', which the frame does not list",
    )
    assert await w.active() == "1"


def raise_autonomy(b: dict[str, Any]) -> None:
    b["autonomy"] = {"level": 3, "reason": "a test", "toward_next": "twenty clean runs"}


def change_method(b: dict[str, Any]) -> None:
    s = step(b, "read")
    s["method"] = "statistics"


def loosen_exactness(b: dict[str, Any]) -> None:
    s = step(b, "count")
    s["exactness"] = "tolerant"
    s["checks"] = [{"kind": "approval", "threshold": 100, "role": "operations"}]


def narrow_an_anchor(b: dict[str, Any]) -> None:
    step(b, "count")["checks"][1]["threshold"] = 1000


def remove_the_person(b: dict[str, Any]) -> None:
    b["steps"] = [s for s in b["steps"] if s["id"] != "review"]
    b["takeover"]["steps"].pop("review", None)


def widen_reach(b: dict[str, Any]) -> None:
    step(b, "read")["work"]["operation"] = "mail.messages.send"


def widen_credentials(b: dict[str, Any]) -> None:
    step(b, "read")["work"]["credentials"] = [{"name": "issues"}]


@pytest.mark.parametrize(
    ("edit", "said"),
    [
        (raise_autonomy, "raises"),
        (change_method, "changes the method of step 'read'"),
        (loosen_exactness, "loosens the exactness of step 'count'"),
        (narrow_an_anchor, "narrows the approval of step 'count' by operations"),
        (remove_the_person, "removes the person's step 'review'"),
        (widen_reach, "widens what step 'read' may reach: uses mail.messages"),
        (widen_credentials, "widens what step 'read' may reach: credential issues"),
    ],
    ids=lambda v: v.__name__ if callable(v) else "",
)
async def test_each_change_always_outside_asked_within_the_frame_is_a_proposal_never_a_version(
    edit: Callable[[dict[str, Any]], None], said: str
) -> None:
    w = await World().registered()
    outcome = await w.changed(changed(edit))
    assert outcome.version is None, "never a new version"
    assert outcome.proposal is not None
    assert any(f.startswith(said) for f in outcome.proposal.findings), outcome.proposal.findings
    assert await w.active() == "1" and await w.stored("triage@2") is None
    assert (await w.kinds())[-1] == "process.change_proposed:outside_frame"
