"""The run's projections equal the full computation over the ledger (ADR-0105).

A tenant's ledger is generated with every case the calibration distinguishes: adapters of
several methods, steps of several processes, a model version that changes, a stopped step, a
rehearsal, an estimate that is never finished and a finish without its estimate. The projection
is folded in one pass and in pieces through its stored form; both give the same stored value,
and `scale_for` over the projection gives exactly the factors it gives over every observation.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryPersistence,
    MemoryProjectionStore,
)
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import link
from taktus.components.run.domain.service import budget as budgeting
from taktus.components.run.domain.service.projections import (
    ACTIVITY,
    CALIBRATION,
    Calibration,
    active,
    every_observation,
    step_key,
)
from taktus.ports.ledger import Fact
from taktus.shared.v1 import Consumption, LedgerEntry, LedgerRefs, Method
from taktus.shared.v1.consumption import PriceKinds

AT = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
ADAPTERS = {
    "worker.alpha": Method.WORKER,
    "worker.beta": Method.WORKER,
    "model.gamma": Method.LLM,
    "connector.delta": Method.RULE,
}
PROCESSES = ("intake@1", "intake@2", "review@1")
STEPS = ("a", "b", "c")
MODELS = ("m-one@1", "m-two@1")


def generated(seed: int, runs: int) -> list[LedgerEntry]:
    """A chain of `runs` runs, each with a few steps admitted and finished, in a shuffled but
    reproducible order of runs that overlap."""
    rng = random.Random(seed)  # noqa: S311 — reproducible test data, nothing secret
    facts: list[Fact] = []
    for n in range(runs):
        run_id = f"run_{n}"
        version = rng.choice(PROCESSES)
        rehearsal = True if rng.random() < 0.05 else None
        facts.append(
            Fact(
                kind="run.created",
                refs=LedgerRefs(run_id=run_id, process_version=version),
                rehearsal=rehearsal,
            )
        )
        for step in rng.sample(STEPS, rng.randint(1, len(STEPS))):
            adapter = rng.choice(list(ADAPTERS))
            method = ADAPTERS[adapter]
            model = MODELS[0] if n < runs * 0.7 else rng.choice(MODELS)
            refs = LedgerRefs(run_id=run_id, step_id=step, process_version=version)
            estimate = Consumption(tokens_in=100, tokens_out=rng.randint(10, 60))
            if rng.random() > 0.05:  # a finish without its estimate
                facts.append(
                    Fact(
                        kind="step.admitted",
                        refs=refs,
                        method=method,
                        adapter=adapter,
                        consumption=estimate,
                        rehearsal=rehearsal,
                    )
                )
            roll = rng.random()
            if roll < 0.05:
                continue  # an estimate that is never finished
            outcome = "stopped" if roll < 0.1 else "succeeded"
            named = {model: PriceKinds(input=100, output=10)} if method is Method.WORKER else None
            actual = (
                None
                if roll > 0.97
                else Consumption(
                    tokens_in=rng.randint(50, 250),
                    tokens_out=rng.randint(5, 90),
                    tokens_by_model=named,
                )
            )
            facts.append(
                Fact(
                    kind="step.finished",
                    refs=refs,
                    method=method,
                    adapter=adapter,
                    consumption=actual,
                    outcome=outcome,
                    rehearsal=rehearsal,
                )
            )
        facts.append(Fact(kind="run.finished", refs=LedgerRefs(run_id=run_id)))
    return chain(facts, rng)


def chain(facts: list[Fact], rng: random.Random) -> list[LedgerEntry]:
    entries: list[LedgerEntry] = []
    previous = None
    at = AT
    for fact in facts:
        at += timedelta(minutes=rng.randint(1, 600))
        previous = link(previous, fact, at)
        entries.append(previous)
    return entries


def folded_in_pieces(entries: list[LedgerEntry], pieces: int) -> Calibration:
    state = CALIBRATION.empty()
    size = max(1, len(entries) // pieces)
    for start in range(0, len(entries), size):
        for entry in entries[start : start + size]:
            if CALIBRATION.kinds is None or entry.kind in CALIBRATION.kinds:
                state = CALIBRATION.fold(state, entry)
        state = CALIBRATION.load(CALIBRATION.dump(state))  # through its stored form
    return state


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_calibration_projection_gives_the_factors_of_every_observation(seed: int) -> None:
    entries = generated(seed, runs=400)
    every = every_observation(entries)
    assert len(every) > 4 * budgeting.WINDOW * len(ADAPTERS), "enough to trim"

    whole = CALIBRATION.empty()
    for entry in entries:
        whole = CALIBRATION.fold(whole, entry)
    pieces = folded_in_pieces(entries, 7)
    assert CALIBRATION.dump(pieces) == CALIBRATION.dump(whole)

    kept = whole.observations()
    assert len(kept) < len(every), "the projection keeps less than every observation"
    for adapter, method in ADAPTERS.items():
        for models in (frozenset(), frozenset({MODELS[0]}), frozenset({MODELS[1]})):
            for process in PROCESSES:
                for step in (*STEPS, "never-run"):
                    key = step_key(process, step)
                    arguments = (adapter, method, ("code",))
                    expected = budgeting.scale_for(*arguments, every, models=models, step=key)
                    found = budgeting.scale_for(*arguments, kept, models=models, step=key)
                    assert found == expected, (adapter, models, key)
            assert budgeting.scale_for(adapter, method, (), kept) == budgeting.scale_for(
                adapter, method, (), every
            )


def test_the_activity_projection_names_the_runs_of_every_period() -> None:
    entries = generated(4, runs=300)
    state = ACTIVITY.empty()
    for entry in entries:
        state = ACTIVITY.fold(state, entry)
    stored = ACTIVITY.load(ACTIVITY.dump(state))
    for period in ("day", "week", "month"):
        assert stored.active(period) == active(entries, period), period


async def test_the_projection_brought_up_to_date_equals_the_one_rebuilt_from_the_ledger() -> None:
    """Through the ledger port: a projection read between recordings, then rebuilt."""
    persistence = MemoryPersistence()
    ledger = ChainedLedger(
        MemoryLedgerStore(persistence), FakeClock(AT), MemoryProjectionStore(persistence)
    )
    entries = generated(5, runs=120)
    facts = [
        Fact.model_validate(
            {k: v for k, v in e.document().items() if k not in {"seq", "ts", "prev_hash", "hash"}}
        )
        for e in entries
    ]
    for start in range(0, len(facts), 97):
        async with persistence.transaction("t"):
            for fact in facts[start : start + 97]:
                await ledger.record("t", fact)
        async with persistence.transaction("t"):
            await ledger.project("t", CALIBRATION)
            await ledger.project("t", ACTIVITY)
    async with persistence.transaction("t"):
        projected = CALIBRATION.dump(await ledger.project("t", CALIBRATION))
        activity = ACTIVITY.dump(await ledger.project("t", ACTIVITY))
        recorded = await ledger.entries("t")
        assert CALIBRATION.dump(await ledger.rebuilt("t", CALIBRATION)) == projected
        assert ACTIVITY.dump(await ledger.rebuilt("t", ACTIVITY)) == activity
    whole = CALIBRATION.empty()
    for entry in recorded:
        whole = CALIBRATION.fold(whole, entry)
    assert CALIBRATION.dump(whole) == projected
