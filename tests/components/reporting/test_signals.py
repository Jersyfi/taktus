"""Signals against their corridors, configured by a person and reported to the owner (ADR-0109,
UC-6.13).

The owner-facing channel is the one the composition root wires, with a carrier that records what
it was told to deliver (`fakes/owner_channel.py`), in the owner's German. What the measuring
step recorded, what the process declares, the incident and the intervention are fakes of the
component's ports, so that each condition is held where the component decides it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from fakes.owner_channel import OUTSIDER, OWNER, TENANT, OwnerChannel, owner_channel, people

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.reporting.application.service import (
    Changer,
    ConfigureCorridor,
    CorridorRefused,
    Corridors,
    SignalWatch,
)
from taktus.components.reporting.domain.model import (
    Corridor,
    Level,
    Recorded,
    ReportKind,
    ReportState,
)
from taktus.components.reporting.ports import Declared, InterventionRefused, RedSignal
from taktus.shared.v1 import ExactnessClass, Method, StepId

CASE = "https://tickets.example/board/cost"
VIEW = "https://taktus.example"


@dataclass
class Steps:
    method: Method = Method.RULE
    exactness: ExactnessClass | None = ExactnessClass.SOURCED

    async def declared(self, tenant: str, process: str, step: StepId) -> Declared | None:
        if (process, step) != ("read-cost", "read"):
            return None
        return Declared(method=self.method, exactness=self.exactness)


@dataclass
class Measured:
    attempts: list[Recorded] = field(default_factory=list)

    async def recorded(
        self, tenant: str, process: str, step: StepId, *, since: datetime
    ) -> Sequence[Recorded]:
        return [a for a in self.attempts if a.at >= since and a.step_id == step]

    async def newest(self, tenant: str, process: str) -> int | None:
        return max((a.seq for a in self.attempts), default=None)


@dataclass
class Incidents:
    raised: list[RedSignal] = field(default_factory=list)

    async def raise_red(self, tenant: str, red: RedSignal) -> str:
        self.raised.append(red)
        return "inc_" + red.run_id


@dataclass
class Starts:
    started: list[tuple[str, str]] = field(default_factory=list)
    refuse: bool = False

    async def start(
        self, tenant: str, process: str, *, by: str, report: str, channel: str, address: str
    ) -> str:
        if self.refuse:
            raise InterventionRefused("not now")
        self.started.append((process, by))
        return f"run_started_{len(self.started)}"


class World:
    def __init__(self) -> None:
        self.given: OwnerChannel = owner_channel()
        self.steps = Steps()
        self.measured = Measured()
        self.incidents = Incidents()
        self.starts = Starts()
        persistence = self.given.persistence
        self.corridors = Corridors(
            MemoryRepository(persistence, Corridor),
            persistence,
            self.given.identity.ledger,
            self.given.clock,
            self.given.identity.directory,
            self.steps,
            self.given.owner.channel,
        )
        self.watch = SignalWatch(
            self.corridors,
            self.measured,
            self.incidents,
            self.given.owner.channel,
            self.given.owner.queries,
            self.given.owner.raising,
            self.given.clock,
        )
        self.given.owner.answering.intervene_with(self.starts)
        self.n = 0

    async def ready(self) -> None:
        await people(self.given)
        await self.given.configure(view_base=VIEW)

    async def configure(self, signal: str = "cost.cloud_daily", **fields: Any) -> Corridor:
        given: dict[str, Any] = {
            "process": "read-cost",
            "step": "read",
            "select": "eur",
            "bounds": "fixed",
            "yellow": 100.0,
            "red": 150.0,
            "role": "owner",
            "case": CASE,
            "interventions": ("throttle-cloud",),
        }
        given.update(fields)
        return await self.corridors.configure(
            ConfigureCorridor(tenant=TENANT, signal=signal, fields=given),
            by=Changer(identity=OWNER),
        )

    def measure(self, value: Any, *, succeeded: bool = True, step: str = "read") -> Recorded:
        self.n += 1
        one = Recorded(
            run_id=f"run_{self.n}",
            step_id=step,
            process_version="read-cost@1",
            seq=self.n,
            at=self.given.clock.now(),
            succeeded=succeeded,
            method=Method.RULE,
            exactness=ExactnessClass.SOURCED,
            provenance=True,
            result={"eur": value},
        )
        self.measured.attempts.append(one)
        return one

    @property
    def said(self) -> list[str]:
        return [s.text for s in self.given.deliveries.said]

    async def entries(self, kind: str) -> list[Any]:
        async with self.given.persistence.transaction(TENANT):
            return [e for e in await self.given.identity.ledger.entries(TENANT) if e.kind == kind]

    def at(self, hour: int, minute: int = 0) -> None:
        now = self.given.clock.current
        self.given.clock.current = now.replace(hour=hour, minute=minute) + timedelta(days=1)


# --- a corridor is configuration, versioned, and a person's ------------------------------------


async def test_each_change_is_a_version_with_who_made_it_and_when() -> None:
    w = World()
    await w.ready()
    first = await w.configure()
    second = await w.configure(red=200.0)
    assert (first.id, second.id) == ("cost.cloud_daily@1", "cost.cloud_daily@2")
    assert second.yellow == 100.0, "what a change leaves out stays"
    history = await w.corridors.history(TENANT, "cost.cloud_daily")
    assert [(h.corridor.version, h.actor) for h in history] == [(1, OWNER), (2, OWNER)]
    assert history[1].corridor.changed_at > history[0].corridor.changed_at
    assert [c.id for c in await w.corridors.current(TENANT)] == ["cost.cloud_daily@2"]
    entries = await w.entries("corridor.changed")
    assert [(e.refs.actor, e.outcome) for e in entries] == [(OWNER, "configured")] * 2


@pytest.mark.parametrize(
    ("by", "reason"),
    [
        (Changer(identity=OWNER, run_id="run_7"), "process"),
        (Changer(identity=OWNER, assignment_id="asg_7"), "worker"),
        (Changer(identity="idn_nobody"), "unknown"),
    ],
)
async def test_a_process_or_a_worker_that_changes_a_corridor_is_refused_and_recorded(
    by: Changer, reason: str
) -> None:
    w = World()
    await w.ready()
    with pytest.raises(CorridorRefused) as refused:
        await w.corridors.configure(
            ConfigureCorridor(tenant=TENANT, signal="cost.cloud_daily", fields={}), by=by
        )
    assert refused.value.reason == reason
    assert await w.corridors.every(TENANT) == [], "nothing changed"
    (entry,) = await w.entries("corridor.refused")
    assert entry.outcome == reason and entry.refs.actor == by.identity
    assert (entry.refs.run_id, entry.refs.assignment_id) == (by.run_id, by.assignment_id)


async def test_a_corridor_that_names_a_person_is_refused() -> None:
    """A signal about people's work is a role's or a department's (principle 14)."""
    w = World()
    await w.ready()
    with pytest.raises(CorridorRefused, match="measures no named person"):
        await w.configure(about={"kind": "role", "name": OUTSIDER})
    with pytest.raises(CorridorRefused):
        await w.configure(signal=OUTSIDER)
    assert [e.outcome for e in await w.entries("corridor.refused")] == ["person", "person"]
    about = await w.configure(about={"kind": "department", "name": "support"})
    assert about.about.name == "support"


@pytest.mark.parametrize(
    ("method", "exactness"),
    [
        (Method.LLM, ExactnessClass.FREE),
        (Method.ML, ExactnessClass.SOURCED),
        (Method.RULE, ExactnessClass.TOLERANT),
    ],
)
async def test_a_corridor_on_a_step_that_cannot_measure_is_refused(
    method: Method, exactness: ExactnessClass
) -> None:
    w = World()
    await w.ready()
    w.steps.method, w.steps.exactness = method, exactness  # the process declares this step
    with pytest.raises(ValueError, match="measured by a rule or statistics"):
        await w.configure()
    with pytest.raises(ValueError, match="no step"):
        await w.configure(step="other")


async def test_a_role_the_channel_does_not_carry_is_refused() -> None:
    w = World()
    await w.ready()
    with pytest.raises(ValueError, match="carries owner"):
        await w.configure(role="finance")


# --- red at once, yellow in the morning ----------------------------------------------------------


async def test_a_red_value_raises_an_incident_and_reaches_its_role_at_once() -> None:
    w = World()
    await w.ready()
    await w.configure()
    w.measure(80)
    assert (await w.watch.look(TENANT)).incidents == ()
    red = w.measure(412)
    looked = await w.watch.look(TENANT)
    assert looked.incidents == ("inc_" + red.run_id,) and looked.reported == 1
    (raised,) = w.incidents.raised
    assert (raised.run_id, raised.step_id, raised.value, raised.red_at) == (
        red.run_id,
        "read",
        412.0,
        150.0,
    )
    (message,) = w.said
    assert "cost.cloud_daily" in message and "412" in message and "150" in message
    assert (
        f"Run {red.run_id}, step read" in message and f"{VIEW}/app/#/runs/{red.run_id}" in message
    )
    assert CASE in message and "inc_" + red.run_id in message
    assert await w.watch.look(TENANT) == type(looked)(), "nothing new is judged again"
    assert len(w.said) == 1


async def test_a_yellow_value_waits_for_the_daily_report() -> None:
    w = World()
    await w.ready()
    await w.configure()
    w.at(5)
    w.measure(120)
    looked = await w.watch.look(TENANT)
    assert [j.level for j in looked.judged] == [Level.YELLOW]
    assert w.incidents.raised == [] and w.said == []
    assert await w.watch.daily(TENANT) is None, "before the hour"
    w.given.clock.current += timedelta(hours=1)
    report = await w.watch.daily(TENANT)
    assert report is not None and report.kind is ReportKind.SIGNALS
    assert any(line.startswith("YELLOW cost.cloud_daily: 120") for line in report.needed)


# --- the daily report ------------------------------------------------------------------------


async def test_the_daily_report_lists_only_what_deviates_and_names_what_was_not_measured() -> None:
    w = World()
    await w.ready()
    await w.configure("cost.cloud_daily")
    await w.configure("errors.rate", step="read", select="errors", yellow=5.0, red=10.0)
    await w.configure(
        "credit.days_left", step="read", select="days", direction="below", yellow=14.0, red=7.0
    )
    w.measured.attempts.append(
        Recorded(
            run_id="run_m",
            step_id="read",
            process_version="read-cost@1",
            seq=1,
            at=w.given.clock.now(),
            succeeded=True,
            method=Method.RULE,
            exactness=ExactnessClass.SOURCED,
            provenance=True,
            result={"eur": 120, "errors": 2, "days": "unknown"},
        )
    )
    report = await w.watch.daily(TENANT)
    assert report is not None and report.id.startswith("signals-")
    lines = report.needed
    assert len(lines) == 2, "the normal error rate is not listed"
    assert lines[0].startswith("YELLOW cost.cloud_daily") and "Run run_m, step read" in lines[0]
    assert lines[1].startswith("NOT MEASURED credit.days_left") and "no number" in lines[1]
    assert all(f"Case: {CASE}" in line for line in lines), "every line carries its case"
    assert all(f"{VIEW}/app/#/runs/run_m" in line for line in lines), "and links its run"
    assert "1 outside their corridor, 1 not measured" in report.title
    assert [o.label for o in report.offered] == ["erledigt", "starte throttle-cloud"]
    (message,) = w.said
    assert message.startswith("*Signale: Signals of") and "starte throttle-cloud" in message
    assert await w.watch.daily(TENANT) is None, "raised once a day"


async def test_the_daily_report_says_so_when_nothing_deviates() -> None:
    w = World()
    await w.ready()
    await w.configure()
    w.measure(80)
    report = await w.watch.daily(TENANT)
    assert report is not None
    assert report.needed == ("Nothing left its corridor: the one signal was measured within it.",)
    assert "every signal within its corridor" in report.title
    assert [o.id for o in report.offered] == ["done"], "nothing to intervene on"


async def test_a_missing_measurement_is_never_shown_as_normal() -> None:
    w = World()
    await w.ready()
    await w.configure()
    w.measure(80, succeeded=False)
    report = await w.watch.daily(TENANT)
    assert report is not None
    assert report.needed[0].startswith("No signal left its corridor: 0 measured within it, 1 not")
    assert report.needed[1].startswith("NOT MEASURED cost.cloud_daily: its newest attempt failed")


async def test_a_tenant_without_a_corridor_gets_no_daily_report() -> None:
    w = World()
    await w.ready()
    assert await w.watch.daily(TENANT) is None


# --- a reply that intervenes ------------------------------------------------------------------


async def deviating_report(w: World) -> Any:
    await w.ready()
    await w.configure()
    w.measure(120)
    report = await w.watch.daily(TENANT)
    assert report is not None
    return report


async def test_a_reply_that_intervenes_is_confirmed_before_its_process_starts() -> None:
    w = World()
    report = await deviating_report(w)
    read = await w.given.answer(report, "Starte throttle-cloud", event="Ev1")
    assert read.outcome == "reflected" and w.starts.started == [], "nothing runs yet"
    assert "start:throttle-cloud" in w.said[-1]
    done = await w.given.answer(report, "ja", event="Ev2")
    assert done.outcome == "filed"
    assert w.starts.started == [("throttle-cloud", OWNER)]
    assert done.report.state is ReportState.FILED and done.report.filed is not None
    assert done.report.filed.record == "run_started_1"
    assert w.said[-1] == "throttle-cloud läuft als Lauf run_started_1."


async def test_a_reading_rejected_or_from_someone_not_named_starts_nothing() -> None:
    w = World()
    report = await deviating_report(w)
    await w.given.answer(report, "starte throttle-cloud", event="Ev1")
    rejected = await w.given.answer(report, "nein", event="Ev2")
    assert rejected.outcome == "reread"
    outsider = await w.given.answer(report, "starte throttle-cloud", OUTSIDER, event="Ev3")
    assert outsider.outcome == "not_filed"
    unknown = await w.given.answer(report, "starte something-else", event="Ev4")
    assert unknown.outcome == "asked_back"
    assert w.starts.started == []


async def test_an_intervention_that_cannot_start_leaves_the_report_open() -> None:
    w = World()
    w.starts.refuse = True
    report = await deviating_report(w)
    await w.given.answer(report, "starte throttle-cloud", event="Ev1")
    refused = await w.given.answer(report, "ja", event="Ev2")
    assert refused.outcome == "refused" and refused.report.state is ReportState.OPEN
    done = await w.given.answer(report, "erledigt", event="Ev3")
    assert done.outcome == "reflected"
