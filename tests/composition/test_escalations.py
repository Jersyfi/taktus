"""A failure's escalation delivered with its situation package, and watched against its time to
react (UC-4.5, ADR-0252), over the memory stores.

What is real: the run engine, registration, the owner-facing channel as the composition root
wires it, the governance component's package, the watch. What is faked: the connector the step
calls, which cannot be reached, and the carrier of the channel, which records what it is told.

What is proven: an escalation reaches the role the process names as a report with five parts,
none empty; a package whose record lacks a part says which; a process that names the path
`ledger` is recorded only; a time to react and its path are the version's; an escalation still
unanswered past its time is recorded once, and one the person reacted to is not.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from fakes import FakeConnector, FakeIdentifiers, FakeWorker
from fakes.connector import WRITE
from fakes.maturity import VERIFIED
from fakes.owner_channel import OWNER, TENANT, owner_channel
from fakes.takeover import instructed

from taktus.adapters.driven.connectors.pool import StaticConnectorPool
from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryRepository,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.governance.domain.model.escalation import Escalated
from taktus.components.governance.domain.service import escalations as rule
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
    parse_bundle,
)
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.reporting.domain.service.backlog import PER_LOOK
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run, RunState
from taktus.composition.escalations import EscalationWatch, report_id
from taktus.ports.ledger import Fact
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, LedgerRefs, Plan, ReplyTo


def bundle(escalation: dict[str, Any] | None) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": "notify",
        "version": "1",
        "name": "Notify",
        "autonomy": {"level": 3, "reason": "a test", "toward_next": "nothing"},
        "limits": {"quota": {"units": 6}},
        "steps": [
            {
                "id": "prepare",
                "method": "rule",
                "reason": "a fixed value",
                "rejected": [],
                "exactness": "exact",
                "checks": [{"kind": "recomputation"}],
                "work": {"rule": "constant", "value": 1},
            },
            {
                "id": "send",
                "method": "rule",
                "reason": "the record is created with fixed fields",
                "rejected": [],
                "exactness": "tolerant",
                "depends_on": ["prepare"],
                "work": {"rule": "connector", "operation": WRITE, "input": {"n": 1}},
            },
        ],
    }
    if escalation is not None:
        document["escalation"] = escalation
    return instructed(document)


class World:
    def __init__(self) -> None:
        self.given = owner_channel()
        self.persistence = self.given.persistence
        self.clock = self.given.clock
        self.ledger = self.given.identity.ledger
        self.runs = MemoryRepository(self.persistence, Run)
        self.versions = MemoryRepository(self.persistence, ProcessVersion)
        self.connector = FakeConnector(unreachable="the service does not answer")
        self.engine = RunEngine(
            maturities=VERIFIED,
            runs=self.runs,
            work=self.persistence,
            objects=MemoryObjectStore(),
            ledger=self.ledger,
            provenance=MemoryProvenanceStore(self.persistence),
            workers=StaticWorkerPool([("worker.fake", FakeWorker())]),
            clock=self.clock,
            ids=FakeIdentifiers(),
            telemetry=NoTelemetry(),
            connectors=StaticConnectorPool([("connector.fake", self.connector)]),
        )
        self.register = RegisterProcessVersionHandler(
            self.versions,
            self.persistence,
            MemoryRepository(self.persistence, Process),
            ledger=self.ledger,
        )
        self.commission = CommissionPlanHandler(
            MemoryRepository(self.persistence, Command),
            MemoryRepository(self.persistence, Plan),
            self.persistence,
            self.clock,
            FakeIdentifiers(),
        )
        self.watch = EscalationWatch(
            ledger=self.ledger,
            runs=self.runs,
            versions=self.versions,
            work=self.persistence,
            clock=self.clock,
            channels=self.given.owner.channel,
            raising=self.given.owner.raising,
            reports=self.given.owner.queries,
        )

    async def escalated(self, escalation: dict[str, Any] | None) -> Run:
        await self.given.configure()
        document = bundle(escalation)
        await self.register.execute(RegisterProcessVersion(document, tenant=TENANT, by=OWNER))
        version = parse_bundle(document)
        command = Command(
            id="cmd_1",
            channel="channel.web",
            identity=OWNER,
            org_path=(TENANT,),
            intent=Intent(raw="notify", recognised="process.run"),
            context={},
            reply_to=ReplyTo(channel="channel.web", address="ledger"),
            received_at=self.clock.now(),
        )
        plan = await self.commission.execute(
            CommissionPlan(
                command=command,
                tenant=TENANT,
                goal="notify",
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        run = await self.engine.start(
            StartRun(
                plan=plan,
                work=version.work,
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=OWNER,
                tenant=TENANT,
            )
        )
        assert run.state is RunState.ESCALATED, run
        return run

    async def kinds(self, prefix: str) -> list[tuple[str, str | None]]:
        async with self.persistence.transaction(TENANT):
            entries = await self.ledger.entries(TENANT)
        return [(e.kind, e.outcome) for e in entries if e.kind.startswith(prefix)]


async def test_an_escalation_reaches_the_named_role_with_five_parts_none_empty() -> None:
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "30m"})
    done = await world.watch.look(TENANT)
    assert done.delivered == (run.id,)
    report = await world.given.owner.queries.one(TENANT, report_id(run.id, 1))
    assert report is not None and report.kind is ReportKind.FAILURE
    assert "step send" in report.title and "lacks" not in report.title
    assert any("by hand" in n for n in report.needed), "the documentation needed"
    assert any("Access to" in n for n in report.needed), "the access needed"
    assert any("Risk:" in s for s in report.steps), "the options with their risks"
    assert any("started" in s for s in report.standing_still), "what was tried"
    assert any("left the system" in s for s in report.standing_still), "what is affected"
    assert await world.kinds("escalation.") == [("escalation.delivered", "complete")]
    again = await world.watch.look(TENANT)
    assert again.delivered == (), "an escalation is delivered once"


async def test_a_package_whose_record_lacks_a_part_says_which() -> None:
    record = Escalated(
        run_id="run_9",
        process_version="p@1",
        escalated_at=World().clock.now(),
        step_id="send",
        cause="failure",
    )
    situation = rule.package(record)
    assert situation.lacking == ("needed",), "no instructions by hand: nothing names the access"
    assert rule.outcome(situation) == "lacking_needed"
    assert rule.package(record.model_copy(update={"step_id": None})).lacking[0] == "happened"


async def test_the_path_ledger_records_the_package_and_raises_no_report() -> None:
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "1h", "path": "ledger"})
    await world.watch.look(TENANT)
    assert await world.given.owner.queries.one(TENANT, report_id(run.id, 1)) is None
    assert await world.kinds("escalation.") == [("escalation.delivered", "complete_ledger")]


async def test_an_unanswered_escalation_past_its_time_is_recorded_once() -> None:
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "30m"})
    await world.watch.look(TENANT)
    assert (await world.watch.look(TENANT)).overdue == (), "within its time"
    world.clock.current += timedelta(minutes=31)
    assert (await world.watch.look(TENANT)).overdue == (run.id,)
    assert (await world.watch.look(TENANT)).overdue == (), "recorded once"
    assert ("escalation.overdue", "unanswered") in await world.kinds("escalation.")


async def test_an_escalation_the_person_reacted_to_is_never_overdue() -> None:
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "30m"})
    await world.watch.look(TENANT)
    async with world.persistence.transaction(TENANT):
        await world.runs.put(TENANT, run.model_copy(update={"state": RunState.HALTED}))
    world.clock.current += timedelta(hours=2)
    assert (await world.watch.look(TENANT)).overdue == ()


async def test_without_a_declaration_the_owner_hears_and_nothing_is_ever_overdue() -> None:
    world = World()
    run = await world.escalated(None)
    await world.watch.look(TENANT)
    assert await world.given.owner.queries.one(TENANT, report_id(run.id, 1)) is not None
    world.clock.current += timedelta(days=3)
    assert (await world.watch.look(TENANT)).overdue == ()


def test_a_version_carries_its_time_to_react_and_path_and_refuses_a_bad_one() -> None:
    import pytest

    from taktus.components.process.domain.model import InvalidProcess

    version = parse_bundle(bundle({"role": "support", "react_within": "2h", "path": "ledger"}))
    assert version.escalation is not None
    assert version.escalation.react_within == timedelta(hours=2)
    assert version.escalation.path == "ledger" and version.escalation.role == "support"
    for wrong in (
        {"role": "support", "react_within": "2h", "path": "pager"},
        {"role": "Support Person", "react_within": "2h"},
        {"role": "support", "react_within": 0},
        {"role": "support", "react_within": "2h", "whom": "x"},
    ):
        with pytest.raises(InvalidProcess):
            parse_bundle(bundle(wrong))


# --- a backlog is never a flood (ADR-0316 §1) ----------------------------------------------------


async def history(world: World, run: Run, n: int, *, ago: timedelta, waiting: bool) -> list[str]:
    """`n` escalations of earlier runs, as an instance upgraded with history holds them: each run
    escalated `ago` before now, and still escalated where `waiting`."""
    now = world.clock.current
    world.clock.current = now - ago
    made: list[str] = []
    state = RunState.ESCALATED if waiting else RunState.HALTED
    for i in range(n):
        suffix = f"w{i}" if waiting else f"s{i}"
        old = run.model_copy(update={"id": f"{run.id}_{suffix}", "state": state})
        async with world.persistence.transaction(TENANT):
            await world.runs.put(TENANT, old)
            await world.ledger.record(
                TENANT,
                Fact(
                    kind="run.escalated",
                    refs=LedgerRefs(
                        tenant=TENANT,
                        run_id=old.id,
                        process_version=old.process_version,
                        step_id="send",
                    ),
                    outcome="failure",
                ),
            )
        made.append(old.id)
    world.clock.current = now
    return made


def summary_of(text: str) -> str:
    """The summary report a message names, by the identifier it carries."""
    match = re.search(r"\((escalations-[^)]+)\)", text)
    assert match is not None, text
    return match.group(1)


async def test_an_upgraded_instance_s_history_is_never_delivered_as_a_flood() -> None:
    """The case of 2026-11-14: the watch starts fresh on an instance with weeks of escalations.
    The current one is delivered on its own; those still open are summarised in one message;
    those settled long ago say nothing; and nothing is said twice."""
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "30m"})
    waiting = await history(world, run, 40, ago=timedelta(days=30), waiting=True)
    settled = await history(world, run, 45, ago=timedelta(days=30), waiting=False)
    world.given.deliveries.said.clear()

    done = await world.watch.look(TENANT)

    assert done.delivered == (run.id,), "only the current escalation on its own"
    said = [s.text for s in world.given.deliveries.said]
    assert len(said) == 2, "the current one, and one summary of the open backlog"
    assert said[1].startswith("*Störung: 40 ältere Eskalationen sind offen*")
    summary = await world.given.owner.queries.one(TENANT, summary_of(said[1]))
    assert summary is not None and len(summary.needed) == len(waiting), "the record lists each"
    outcomes = [o for k, o in await world.kinds("escalation.") if k == "escalation.not_sent"]
    assert outcomes.count("summarised") == len(waiting)
    assert outcomes.count("settled") == len(settled)
    assert (await world.watch.look(TENANT)).delivered == ()
    assert len(world.given.deliveries.said) == 2, "nothing is said twice"
    world.clock.current += timedelta(days=3)
    assert (await world.watch.look(TENANT)).overdue == (run.id,), "only one delivered is watched"


async def test_more_current_escalations_than_the_limit_are_summarised_beyond_it() -> None:
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "30m"})
    await history(world, run, 6, ago=timedelta(minutes=5), waiting=True)
    world.given.deliveries.said.clear()

    done = await world.watch.look(TENANT)

    assert len(done.delivered) == PER_LOOK, "at most three on their own per role and look"
    said = world.given.deliveries.said
    assert len(said) == PER_LOOK + 1, "and one summary of the four others"
    assert said[-1].text.startswith("*Störung: 4 ältere Eskalationen")


async def test_an_escalation_s_message_is_short_in_one_language_and_names_the_process() -> None:
    """The message is the package's short form (ADR-0316 §2): the process by its name, the
    failure on one quoted line, the options in a few words; the package stays in the record."""
    world = World()
    run = await world.escalated({"role": "owner", "react_within": "30m"})
    await world.watch.look(TENANT)
    (said,) = [s.text for s in world.given.deliveries.said]
    assert said.splitlines()[0] == "*Störung: Notify steht bei Schritt send*"
    assert run.id not in said.replace(f"({report_id(run.id, 1)})", "")
    assert "notify@" not in said and "lacks" not in said and "Risk" not in said
    assert len(said) <= 400, said
    report = await world.given.owner.queries.one(TENANT, report_id(run.id, 1))
    assert report is not None and any("Risk:" in s for s in report.steps), "the record is whole"
