"""What needs a person's action reaches the owner's channel (ADR-0106, issue #323).

Each of the signals — a capacity crossing to *act*, a lost claim, a failed or missing
backup, a level that fell by rule or a raise Taktus proposes (ADR-0110) — is recorded as its
producer records it: the ledger entry of the capacity report and of the runner, the row of the
backup program, the governance component's incident and entry. The owner-facing channel is the
one the composition root wires, with a carrier that records what it was told to deliver
(`fakes/owner_channel.py`). Each produces one message, with what happened and what to do; a
repeated look sends nothing new until it clears. Without a channel, nothing is sent, the view
says why, and the startup log says which tenant hears nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from fakes import FakeClock
from fakes.identity import FixedTenants
from fakes.owner_channel import CHANNEL, SECRET, TENANT, OwnerChannel, owner_channel

from taktus.adapters.driven.memory import MemoryBackupLog, MemoryTenantStore
from taktus.components.governance.application.service import (
    BreachSeen,
    ConfigureCorrections,
    DecisionMade,
)
from taktus.components.reporting.application.service import Alerts, Reported
from taktus.components.reporting.domain.model import ReportKind
from taktus.components.run.application.service import CLAIM_LOST
from taktus.composition.alerts import alerts, alerts_tick, say_who_hears
from taktus.ports.backups import BackupOutcome
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

DATABASE = "capacity.storage.database"


class World:
    def __init__(self, *, expected_hours: int | None = 26) -> None:
        self.given: OwnerChannel = owner_channel()
        self.backups = MemoryBackupLog(self.given.persistence)
        self.alerts: Alerts = alerts(
            self.given.identity.ledger,
            self.given.persistence,
            self.backups,
            MemoryTenantStore(self.given.persistence),
            self.given.owner,
            self.given.clock,
            backup_expected_hours=expected_hours,
            corrections=self.given.decisions.corrections,
        )
        # A backup a moment ago: only the signal a test records is in effect.
        self.backed_up(ok=True)

    @property
    def said(self) -> list[str]:
        return [s.text for s in self.given.deliveries.said]

    async def record(self, kind: str, *, outcome: str, run_id: str | None = None) -> None:
        async with self.given.persistence.transaction(TENANT):
            await self.given.identity.ledger.record(
                TENANT,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=TENANT, run_id=run_id),
                    adapter="platform.host" if kind.startswith("capacity.") else None,
                    outcome=outcome,
                ),
            )

    def backed_up(self, *, ok: bool, reason: str = "store") -> None:
        at = self.given.clock.now()
        self.backups.record(
            TENANT,
            BackupOutcome(
                name="taktus-" + at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
                at=at,
                outcome="ok" if ok else "failed",
                reason=None if ok else reason,
            ),
        )

    def later(self, **delta: float) -> None:
        self.given.clock.current += timedelta(**delta)

    async def done(self, report_id: str) -> None:
        """The owner answers the report that it is done, and confirms the reading."""
        report = await self.given.owner.queries.one(TENANT, report_id)
        assert report is not None
        await self.given.answer(report, "erledigt", event=f"{report_id}-1")
        await self.given.answer(report, "ja", event=f"{report_id}-2")


async def test_a_capacity_finding_that_turns_to_act_is_said_once_until_it_clears() -> None:
    w = World()
    await w.given.configure()
    await w.record(DATABASE, outcome="act")

    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    (message,) = w.said
    assert "storage (database)" in message and DATABASE in message
    assert "taktusctl capacity" in message, "what to do"
    w.later(hours=2)
    assert await w.alerts.report(TENANT) == Reported(), "a repeated look sends nothing new"

    await w.record(DATABASE, outcome="ok")
    (cleared,) = await w.alerts.noticed(TENANT)
    assert not cleared.alert.in_effect and cleared.delivered
    assert await w.alerts.report(TENANT) == Reported()

    await w.record(DATABASE, outcome="act")
    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    assert len(w.said) == 2, "after it cleared, a new crossing is a new message"


async def test_a_runner_that_lost_its_claim_is_one_message_until_it_is_answered_done() -> None:
    w = World()
    await w.given.configure()
    await w.record(CLAIM_LOST, outcome="lost", run_id="run_1")
    await w.record(CLAIM_LOST, outcome="lost", run_id="run_2")

    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    (message,) = w.said
    assert "run_1" in message and "run_2" in message and "TAKTUS_LEASE_SECONDS" in message
    await w.record(CLAIM_LOST, outcome="lost", run_id="run_3")
    assert await w.alerts.report(TENANT) == Reported(), "one alert holds every loss"

    (one,) = await w.alerts.noticed(TENANT)
    await w.done(one.alert.id)
    (closed,) = await w.alerts.noticed(TENANT)
    assert closed.closed
    w.later(minutes=5)
    await w.record(CLAIM_LOST, outcome="lost", run_id="run_4")
    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    assert "run_4" in w.given.deliveries.said[-1].text


async def test_a_failed_backup_is_said_with_its_step_and_clears_with_the_next_success() -> None:
    w = World()
    await w.given.configure()
    w.backed_up(ok=False, reason="store")

    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    message = w.said[-1]
    assert "`store`" in message and "backup store" in message
    w.later(hours=24)
    w.backed_up(ok=False, reason="database")
    assert await w.alerts.report(TENANT) == Reported(), "the same failure, said once"

    w.backed_up(ok=True)
    assert await w.alerts.noticed(TENANT) == ()
    assert await w.alerts.report(TENANT) == Reported()
    w.backed_up(ok=False, reason="retention")
    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)


async def test_a_missing_backup_is_said_once_the_expected_interval_has_passed() -> None:
    w = World(expected_hours=26)
    await w.given.configure()
    w.later(hours=25)
    assert await w.alerts.report(TENANT) == Reported()
    w.later(hours=2)
    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    assert "none succeeded in the last 26 hours" in w.said[-1]
    w.later(hours=24)
    assert await w.alerts.report(TENANT) == Reported(), "still missing, said once"
    w.backed_up(ok=True)
    assert await w.alerts.noticed(TENANT) == ()


async def test_a_tenant_never_backed_up_counts_from_its_creation_and_unwatched_says_nothing() -> (
    None
):
    w = World(expected_hours=26)
    w.backups = MemoryBackupLog(w.given.persistence)  # no backup was ever recorded
    w.alerts = alerts(
        w.given.identity.ledger, w.given.persistence, w.backups,
        MemoryTenantStore(w.given.persistence), w.given.owner, w.given.clock,
        backup_expected_hours=26,
    )  # fmt: skip
    await w.given.configure()
    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    assert "No successful backup was ever recorded" in w.said[-1]

    unwatched = World(expected_hours=None)
    unwatched.later(days=30)
    assert await unwatched.alerts.noticed(TENANT) == (), "without an interval, none is missing"


async def test_without_a_channel_nothing_is_sent_and_the_view_and_the_startup_log_say_so() -> None:
    w = World()  # no owner-facing channel configured
    await w.record(DATABASE, outcome="act")
    w.backed_up(ok=False)

    assert await w.alerts.report(TENANT) == Reported()
    assert w.said == []
    shown = await w.alerts.noticed(TENANT)
    assert [a.alert.kind for a in shown] == ["capacity", "backup"]
    assert all(not a.delivered and a.reason == "no_channel" for a in shown)
    assert "owner-facing channel" in shown[0].text()

    with structlog.testing.capture_logs() as logs:
        await say_who_hears(w.given.owner, FixedTenants((TENANT,)), backup_expected_hours=26)
    assert any(
        "no owner-facing channel" in line["event"] and line.get("tenant") == TENANT for line in logs
    )
    assert any(line.get("expected_hours") == 26 for line in logs)

    await w.given.configure()
    assert await w.alerts.report(TENANT) == Reported(raised=2, delivered=2)


async def test_every_message_is_a_failure_report_with_no_person_and_no_secret() -> None:
    w = World()
    await w.given.configure()
    await w.record(DATABASE, outcome="act")
    await w.record(CLAIM_LOST, outcome="lost", run_id="run_1")
    w.backed_up(ok=False, reason="encryption")
    assert await w.alerts.report(TENANT) == Reported(raised=3, delivered=3)
    reports = await w.given.owner.queries.reports(TENANT)
    assert {r.kind for r in reports} == {ReportKind.FAILURE}
    assert [s.channel for s in w.given.deliveries.said] == [CHANNEL] * 3
    for text in w.said:
        assert SECRET not in text and "idn_" not in text


async def test_the_scheduler_looks_once_per_interval_and_survives_a_failure() -> None:
    clock = FakeClock(datetime(2026, 10, 18, tzinfo=UTC))

    class Failing:
        def __init__(self) -> None:
            self.looked: list[str] = []

        async def report(self, tenant: str) -> Reported:
            self.looked.append(tenant)
            raise RuntimeError("the ledger did not answer")

    found = Failing()
    tick = alerts_tick(found, FixedTenants(("a", "b")), clock, interval_seconds=60)  # type: ignore[arg-type]
    await tick()
    await tick()
    assert found.looked == ["a", "b"]
    clock.current += timedelta(seconds=61)
    await tick()
    assert found.looked == ["a", "b", "a", "b"]


async def test_a_level_that_fell_by_rule_reaches_the_owner_until_answered() -> None:
    """ADR-0110: the owner hears of a lowering, with its rule and its levels."""
    w = World()
    await w.given.configure()
    corrections = w.given.decisions.corrections
    await corrections.breached(
        TENANT,
        BreachSeen(
            process_version="p@1", run_id="run_1", step_id="send", level=3, anchors=("anc-w",)
        ),
    )

    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    (message,) = w.said
    assert "now runs at level 2" in message and "anc-w" in message and "run_1" in message
    assert "--approve-raise" in message, "how it rises again"
    w.later(hours=2)
    assert await w.alerts.report(TENANT) == Reported(), "said once"
    (one,) = await w.alerts.noticed(TENANT)
    await w.done(one.alert.id)
    (closed,) = await w.alerts.noticed(TENANT)
    assert closed.closed
    assert (await corrections.lowered(TENANT, "p@1")).level == 2, "an answer raises nothing"


async def test_a_raise_taktus_proposes_reaches_the_owner_with_its_figures() -> None:
    w = World(expected_hours=None)
    await w.given.configure()
    corrections = w.given.decisions.corrections
    await corrections.configure(
        ConfigureCorrections(tenant=TENANT, raise_decisions=2, raise_weeks=1), by="idn_owner"
    )
    for days in (0, 8):
        w.later(days=days)
        async with w.given.persistence.transaction(TENANT):
            await w.given.identity.ledger.record(
                TENANT,
                Fact(
                    kind="proposal.decided",
                    refs=LedgerRefs(tenant=TENANT, process_version="p@1", run_id=f"run_{days}"),
                    outcome="released",
                ),
            )
        await corrections.decided(
            TENANT,
            DecisionMade(
                process_version="p@1", run_id=f"run_{days}", step_id="a", action=None, level=2
            ),
        )

    assert await w.alerts.report(TENANT) == Reported(raised=1, delivered=1)
    (message,) = w.said
    assert "proposes raising the process p" in message
    assert "0% of 1 proposal(s) over 7 days" in message and "0% of 2 over 28 days" in message
    assert "never applies a raise" in message
