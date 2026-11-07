"""Processes nobody wrote down (UC-9.4, ADR-0245 §2).

Five stages in order, each a ledger entry; the decision is a person's; a discovered process
enters automation at level 1 or 2 with takeover instructions; a pattern found in a person's own
requests is theirs until they agree; the interview writes the same process in either mode.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeClock, FakeIdentifiers

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.value.application.service import Discoveries
from taktus.components.value.application.service.discovery import TAKTUS, stages_recorded
from taktus.components.value.domain.model import DiscoveredProcess, DiscoveryRefused
from taktus.components.value.domain.service import discovery

TENANT = "default"
AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def found() -> tuple[Discoveries, ChainedLedger, MemoryPersistence]:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), FakeClock(AT))
    return (
        Discoveries(
            MemoryRepository(persistence, DiscoveredProcess),
            ledger,
            persistence,
            FakeClock(AT),
            FakeIdentifiers(),
        ),
        ledger,
        persistence,
    )


async def test_every_stage_is_a_ledger_entry_and_none_is_reached_without_the_one_before() -> None:
    d, ledger, persistence = found()
    record = await d.visible(TENANT, title="Bank check", origin="interview", found="Fridays")
    with pytest.raises(DiscoveryRefused) as early:
        await d.advance(TENANT, record.id, "valued", "idn_ada", minutes_by_hand=10)
    assert early.value.reason == "out_of_order"
    await d.advance(
        TENANT, record.id, "documented", "idn_ada", description="d", owner_role="accounting"
    )
    await d.advance(TENANT, record.id, "valued", "idn_ada", minutes_by_hand=10, cases_per_month=4)
    with pytest.raises(DiscoveryRefused) as machine:
        await d.advance(TENANT, record.id, "decided", TAKTUS, decision="automate")
    assert machine.value.reason == "not_a_person", "Taktus never decides"
    await d.advance(TENANT, record.id, "decided", "idn_ada", decision="automate")
    for level, instructions, reason in ((3, True, "level"), (1, False, "instructions")):
        with pytest.raises(DiscoveryRefused) as refused:
            await d.advance(
                TENANT,
                record.id,
                "automated",
                "idn_ada",
                process_id="p",
                level=level,
                instructions=instructions,
            )
        assert refused.value.reason == reason
    await d.advance(
        TENANT, record.id, "automated", "idn_ada", process_id="p", level=1, instructions=True
    )
    async with persistence.transaction(TENANT):
        entries = list(await ledger.entries(TENANT))
    assert stages_recorded(entries, record.id) == [
        "visible",
        "documented",
        "valued",
        "decided",
        "automated",
    ]
    (decided,) = [e for e in entries if e.kind == "discovery.decided"]
    assert decided.refs.actor == "idn_ada" and decided.outcome == "automate"


async def test_a_pattern_found_for_a_person_is_theirs_until_they_agree() -> None:
    d, _, _ = found()
    record = await d.visible(
        TENANT,
        title="Weekly export",
        origin="pattern",
        found="the export is asked for every Monday",
        reader="idn_ada",
    )
    assert [r.id for r in await d.of(TENANT, "idn_bo")] == [], "nobody else reads it"
    with pytest.raises(DiscoveryRefused):
        await d.get(TENANT, record.id, "idn_bo")
    with pytest.raises(DiscoveryRefused) as early:
        await d.advance(
            TENANT, record.id, "documented", "idn_ada", description="d", owner_role="ops"
        )
    assert early.value.reason == "not_agreed"
    with pytest.raises(DiscoveryRefused):
        await d.agree(TENANT, record.id, "idn_bo")
    shared = await d.agree(TENANT, record.id, "idn_ada")
    assert shared.reader is None, "a procedure of the organisation, its finder not on it"
    assert [r.id for r in await d.of(TENANT, "idn_bo")] == [record.id]


def test_the_interview_writes_the_same_process_in_the_guided_and_the_expert_mode() -> None:
    guided, expert = discovery.questions("guided"), discovery.questions("expert")
    assert [q["key"] for q in guided] == [q["key"] for q in expert]
    assert all("example" in q for q in guided) and not any("example" in q for q in expert)
    answers = {
        "what": "check invoices",
        "when": "Fridays",
        "tools": "bank, mail",
        "owner_role": "Accounting",
        "done": "each is marked",
    }
    assert discovery.documented(answers) == discovery.documented(dict(answers))
    assert discovery.documented(answers).owner_role == "accounting"
    with pytest.raises(ValueError):
        discovery.documented({**answers, "done": " "})


def test_a_request_recurring_in_three_weeks_is_a_pattern_for_its_person() -> None:
    def asked(identity: str, weeks: int) -> list[discovery.Request]:
        return [
            discovery.Request(
                words=f"Export the list for week {n}!",
                identity=identity,
                at=AT + timedelta(weeks=n),
            )
            for n in range(weeks)
        ]

    (pattern,) = discovery.patterns([*asked("idn_ada", 3), *asked("idn_bo", 2)])
    assert (pattern.reader, pattern.request, pattern.weeks) == (
        "idn_ada",
        "export the list for week",
        3,
    )
