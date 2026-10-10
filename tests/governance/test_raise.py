"""Only a person raises an autonomy level, and only on evidence (UC-7.1 §2, ADR-0026, ADR-0039).

A raise is a version whose statement lets a step run at a higher level than the version it
replaces. It is stored only with a person's approval and the quality history the replaced
version names; a refusal is a ledger entry. Taktus may propose a raise; nothing applies one
without the approval.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.propose_raise import (
    ProposeRaise,
    ProposeRaiseHandler,
)
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import (
    InvalidProcess,
    Process,
    ProcessVersion,
    RaiseRefused,
)
from taktus.ports.administration import Administration
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerEntry, LedgerRefs

ROOT = Path(__file__).resolve().parents[2]
TENANT = "t"
PERSON = "idn_person"


def bundle(
    level: int = 2,
    *,
    version: str = "1",
    history: int | None = 3,
    actions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    autonomy: dict[str, Any] = {"level": level, "reason": "r", "toward_next": "t"}
    if history is not None:
        autonomy["history"] = history
    if actions is not None:
        autonomy["actions"] = actions
    return {
        "id": "p",
        "version": version,
        "name": "P",
        "autonomy": autonomy,
        "steps": [
            {
                "id": "build",
                "method": "worker",
                "reason": "r",
                "rejected": [],
                "exactness": "tolerant",
                "fallback": {"when": "x", "to": "human"},
                "requires": ["shell.script"],
                "work": {"task": {"goal": "g", "acceptance": ["a"]}},
            },
            {
                "id": "merge",
                "method": "rule",
                "reason": "r",
                "rejected": [],
                "exactness": "sourced",
                "depends_on": ["build"],
                "work": {"rule": "connector", "operation": "repository.pullrequest.merge"},
            },
        ],
    }


class World:
    def __init__(self, administration: Administration | None = None) -> None:
        self.persistence = MemoryPersistence()
        self.ledger = ChainedLedger(
            MemoryLedgerStore(self.persistence), FakeClock(datetime(2026, 10, 9, tzinfo=UTC))
        )
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.processes = MemoryRepository(self.persistence, Process)
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            self.processes,
            ledger=self.ledger,
            administration=administration,
        )
        self.propose = ProposeRaiseHandler(
            self.versions, self.processes, self.persistence, self.ledger
        )
        self.runs = 0

    async def registered(
        self, document: dict[str, Any], approved_by: str | None = None
    ) -> ProcessVersion:
        return await self.register.execute(
            RegisterProcessVersion(document, tenant=TENANT, approved_by=approved_by)
        )

    async def ran(self, *ends: str) -> None:
        """Runs of p@1 that ended as given: `finished`, `escalated`, or `failed_step` for a run
        that finished after a step of it failed."""
        for end in ends:
            self.runs += 1
            run_id = f"run_{self.runs}"
            refs = LedgerRefs(tenant=TENANT, process_version="p@1", run_id=run_id)
            facts = []
            if end == "failed_step":
                facts.append(Fact(kind="step.finished", refs=refs, outcome="failed"))
            kind = "run.escalated" if end == "escalated" else "run.finished"
            facts.append(Fact(kind=kind, refs=refs, outcome="succeeded"))
            async with self.persistence.transaction(TENANT):
                for fact in facts:
                    await self.ledger.record(TENANT, fact)

    async def entries(self) -> list[LedgerEntry]:
        async with self.persistence.transaction(TENANT):
            return list(await self.ledger.entries(TENANT))

    async def active(self) -> ProcessVersion:
        async with self.persistence.transaction(TENANT):
            process = await self.processes.get(TENANT, "p")
            assert process is not None
            version = await self.versions.get(TENANT, f"p@{process.active_version}")
        assert version is not None
        return version


def autonomy_entries(entries: list[LedgerEntry]) -> list[tuple[str, str | None, str | None]]:
    return [(e.kind, e.outcome, e.refs.actor) for e in entries if e.kind.startswith("autonomy.")]


# --- a raise needs a person's approval and a quality history ---------------------------------


async def test_a_raise_without_a_persons_approval_is_refused_and_recorded() -> None:
    w = World()
    await w.registered(bundle(2))
    await w.ran("finished", "finished", "finished")
    with pytest.raises(RaiseRefused) as refused:
        await w.registered(bundle(3, version="2"))
    assert "approval by a person" in refused.value.findings[0]
    assert autonomy_entries(await w.entries()) == [("autonomy.refused", "no_approval", None)]
    assert (await w.active()).autonomy.level == 2, "nothing of the version was stored"


async def test_a_raise_without_the_history_is_refused_even_with_the_approval() -> None:
    w = World()
    await w.registered(bundle(2))
    await w.ran("finished", "finished", "escalated", "finished", "failed_step", "finished")
    with pytest.raises(RaiseRefused) as refused:
        await w.registered(bundle(3, version="2"), approved_by=PERSON)
    assert "needs 3 runs in a row" in refused.value.findings[0]
    assert "1 of 6 ended run(s)" in refused.value.findings[0]
    assert autonomy_entries(await w.entries()) == [("autonomy.refused", "history_short", PERSON)]
    assert (await w.active()).version == "1"


async def test_a_raise_is_refused_while_the_version_names_no_history() -> None:
    w = World()
    await w.registered(bundle(2, history=None))
    await w.ran(*["finished"] * 10)
    with pytest.raises(RaiseRefused, match="names none"):
        await w.registered(bundle(3, version="2"), approved_by=PERSON)
    assert autonomy_entries(await w.entries())[-1][1] == "no_history_named"


async def test_a_raise_with_both_is_admitted_and_recorded_with_the_person() -> None:
    w = World()
    await w.registered(bundle(2))
    await w.ran("escalated", "finished", "finished", "finished")
    version = await w.registered(bundle(3, version="2", history=1), approved_by=PERSON)
    assert version.autonomy.level == 3
    assert (await w.active()).version == "2"
    assert autonomy_entries(await w.entries()) == [("autonomy.raised", "raised", PERSON)]


async def test_the_history_is_the_replaced_versions_not_the_raising_ones() -> None:
    w = World()
    await w.registered(bundle(2, history=5))
    await w.ran("finished")
    with pytest.raises(RaiseRefused, match="needs 5 runs"):
        await w.registered(bundle(3, version="2", history=1), approved_by=PERSON)


async def test_rehearsals_and_other_processes_are_no_history() -> None:
    w = World()
    await w.registered(bundle(2, history=1))
    async with w.persistence.transaction(TENANT):
        await w.ledger.record(
            TENANT,
            Fact(
                kind="run.finished",
                refs=LedgerRefs(tenant=TENANT, process_version="p@1", run_id="run_r"),
                rehearsal=True,
            ),
        )
        await w.ledger.record(
            TENANT,
            Fact(
                kind="run.finished",
                refs=LedgerRefs(tenant=TENANT, process_version="q@1", run_id="run_q"),
            ),
        )
    with pytest.raises(RaiseRefused, match="0 of 0"):
        await w.registered(bundle(3, version="2"), approved_by=PERSON)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        # an action's level goes up
        (
            {"shell.script": {"level": 1, "reason": "r", "toward_next": "t"}},
            {"shell.script": {"level": 2, "reason": "r", "toward_next": "t"}},
        ),
        # an action loses its entry, and runs at the process's level
        ({"repository.pullrequest.merge": {"level": 1, "reason": "r", "toward_next": "t"}}, None),
    ],
)
async def test_raising_an_actions_level_is_a_raise(
    before: dict[str, Any], after: dict[str, Any] | None
) -> None:
    w = World()
    await w.registered(bundle(2, actions=before))
    with pytest.raises(RaiseRefused, match="the action"):
        await w.registered(bundle(2, version="2", actions=after))


async def test_lowering_a_level_needs_neither() -> None:
    w = World()
    await w.registered(bundle(3))
    lowered = {"shell.script": {"level": 1, "reason": "r", "toward_next": "t"}}
    await w.registered(bundle(3, version="2", actions=lowered))
    await w.registered(bundle(2, version="3", actions=lowered))
    assert (await w.active()).autonomy.level == 2
    assert autonomy_entries(await w.entries()) == []


async def test_a_new_process_sets_its_level_without_a_raise() -> None:
    w = World()
    await w.registered(bundle(3))
    assert autonomy_entries(await w.entries()) == []


# --- Taktus proposes; nothing applies a raise without the approval --------------------------


async def test_a_proposal_carries_the_evidence_and_never_applies_itself() -> None:
    w = World()
    await w.registered(bundle(2))
    await w.ran("finished", "finished", "finished")
    proposal = await w.propose.execute(ProposeRaise(tenant=TENANT, process_id="p"))
    assert proposal.evidenced and proposal.quality.clean == 3 and proposal.required == 3
    assert (await w.active()).autonomy.level == 2, "the proposal changed nothing"
    assert autonomy_entries(await w.entries()) == [("autonomy.proposed", "evidenced", None)]
    with pytest.raises(RaiseRefused, match="approval by a person"):
        await w.registered(bundle(3, version="2"))


def test_no_code_path_stores_a_version_but_the_one_that_asks_for_the_approval() -> None:
    """Every write of a process version goes through `RegisterProcessVersionHandler`, which
    refuses a raise without a person's approval (the tests above). No other code puts a
    version; and the approval is only ever the invoking person's, given with `--approve-raise`."""
    src = ROOT / "src" / "taktus"
    puts = [
        path.relative_to(ROOT).as_posix()
        for path in src.rglob("*.py")
        if re.search(r"versions\.put\(", path.read_text(encoding="utf-8"))
    ]
    assert puts == ["src/taktus/components/process/application/service/register_version.py"]
    approvals = {
        path.relative_to(ROOT).as_posix(): re.findall(r"approved_by=([^,)\n]+)", text)
        for path in src.rglob("*.py")
        if (text := path.read_text(encoding="utf-8")) and "approved_by=" in text
    }
    approvals.pop("src/taktus/components/process/application/service/register_version.py")
    assert approvals == {
        "src/taktus/adapters/driving/cli/run_command.py": [
            "placed.identity if approve_raise else None"
        ],
        "src/taktus/adapters/driving/cli/submit_command.py": [
            "placed.identity if approve_raise else None"
        ],
    }


# --- the statement as the bundle carries it -------------------------------------------------------


def test_an_action_level_above_the_processs_is_refused() -> None:
    above = {"shell.script": {"level": 3, "reason": "r", "toward_next": "t"}}
    with pytest.raises(InvalidProcess, match="above the process's 2"):
        parse_bundle(bundle(2, actions=above))


def test_an_action_no_step_uses_is_refused() -> None:
    unused = {"repository.issues.comment": {"level": 1, "reason": "r", "toward_next": "t"}}
    with pytest.raises(InvalidProcess, match="no step of this process uses"):
        parse_bundle(bundle(2, actions=unused))


def test_an_action_carries_its_reason() -> None:
    with pytest.raises(InvalidProcess, match="reason"):
        parse_bundle(bundle(3, actions={"shell.script": {"level": 2, "toward_next": "t"}}))


# --- a version that would administer the instance's own platform (ADR-0052, issue #83) ----------


def naming(name: Any) -> dict[str, Any]:
    document = bundle()
    document["steps"][1]["work"]["credentials"] = [{"name": name, "injected_as": "env"}]
    return document


async def test_a_version_naming_a_credential_that_administers_this_platform_is_refused() -> None:
    w = World(Administration(platform="here", declared={"KUBE": ("there", "here")}))
    with pytest.raises(InvalidProcess) as refused:
        await w.registered(naming("KUBE"))
    [finding] = refused.value.findings
    assert "'merge'" in finding and "'KUBE'" in finding and "'here'" in finding
    async with w.persistence.transaction(TENANT):
        assert await w.versions.list(TENANT) == []
    assert [(e.kind, e.outcome) for e in await w.entries()] == [("process.refused", "administers")]


async def test_an_undeclared_credential_is_refused_and_a_declared_one_registers() -> None:
    w = World(Administration(platform="here", declared={"TOKEN": ()}))
    with pytest.raises(InvalidProcess, match="undeclared"):
        await w.registered(naming("OTHER"))
    version = await w.registered(naming("TOKEN"))
    assert version.ref == "p@1"


async def test_a_credential_named_by_a_reference_is_left_to_admission() -> None:
    w = World(Administration(platform="here"))
    version = await w.registered(naming({"$input": "credential"}))
    assert version.ref == "p@1"


async def test_without_a_platform_nothing_is_refused() -> None:
    w = World(Administration(declared={"KUBE": ("here",)}))
    assert (await w.registered(naming("KUBE"))).ref == "p@1"
