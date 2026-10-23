"""The trace inside a worker's step, on the HTTP surface (ADR-0135, UC-6.14).

A real engine runs a worker step on the fake worker, which reports what it does; the surface
shows each event with its sentence, every secret value masked, and the ledger holds none of
what the worker said. The trace is shown to the owner's role and to a role it is shared with,
and to nobody else; a share names a role, never a person; a run the reader may not see is
answered as one that does not exist. An event reaches a reader who asks again within 5 seconds.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fakes import FakeWorker, InnerStep
from fakes.maturity import VERIFIED

from taktus.adapters.driven.memory import (
    MemoryObjectStore,
    MemoryProvenanceStore,
    MemoryTraceStore,
)
from taktus.adapters.driven.telemetry import NoTelemetry
from taktus.adapters.driven.workers.pool import StaticWorkerPool
from taktus.components.reporting.domain.model import Reader, RunRef
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import Run
from taktus.composition.owner_channel import KnownSecrets
from taktus.ports.worker import ComputeLimit, Event, Limits
from taktus.shared.v1 import (
    Commissioned,
    ExactnessClass,
    Fallback,
    Method,
    Plan,
    PlanResult,
    PlanStatus,
    Step,
)

from .conftest import OTHER, TENANT, Services, a_run

type Client = tuple[httpx.AsyncClient, Services, str]

AT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)

SECRET = "a-made-up-trace-secret-value"  # noqa: S105 — a test value
"""A secret value the instance holds: no trace may show it."""


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def engine(given: Services, worker: FakeWorker) -> RunEngine:
    return RunEngine(
        maturities=VERIFIED,
        runs=given.runs,
        work=given.persistence,
        objects=MemoryObjectStore(),
        ledger=given.ledger,
        provenance=MemoryProvenanceStore(given.persistence),
        workers=StaticWorkerPool([("worker.fake", worker)]),
        clock=given.clock,
        ids=given.ids,
        telemetry=NoTelemetry(),
        traces=MemoryTraceStore(given.persistence),
        masking=KnownSecrets([SECRET]),
    )


def started(tenant: str = TENANT) -> StartRun:
    step = Step(
        id="w",
        method=Method.WORKER,
        reason="r",
        rejected=(),
        exactness=ExactnessClass.TOLERANT,
        fallback=Fallback(when="x", to=Method.HUMAN),
        requires=("shell.script",),
    )
    return StartRun(
        plan=Plan(
            id="pln_1",
            command_id="cmd_1",
            goal="g",
            autonomy_level=3,
            steps=(step,),
            results_in=PlanResult.RUN,
            status=PlanStatus.COMMISSIONED,
            commissioned=Commissioned(by="idn_t", at=AT),
        ),
        work={"w": {"task": {"goal": "g", "acceptance": ["a"]}}},
        budget=Limits(compute=ComputeLimit(seconds=60, resource_class="cpu.small")),
        process_version="p@1",
        actor="idn_t",
        tenant=tenant,
    )


SCRIPT = (
    InnerStep("plan", said=f"connecting with {SECRET}"),
    InnerStep("edit", said="wrote the change", artifacts=(("diff-1", b"+ one line\n"),)),
)


async def worked(given: Services, tenant: str = TENANT) -> Run:
    return await engine(given, FakeWorker(script=SCRIPT)).start(started(tenant))


async def key(given: Services, name: str, *roles: str, tenant: str = TENANT) -> str:
    _, issued = await given.identity.directory.add(tenant, name, (tenant,), roles=roles)
    return issued


async def test_every_event_is_shown_with_its_sentence_masked_and_the_ledger_holds_none(
    client: Client,
) -> None:
    http, given, base = client
    run = await worked(given)
    owner = await key(given, "idn_ada", "owner")

    answer = await http.get(f"{base}/levels/runs/{run.id}/steps/w/trace", headers=bearer(owner))
    assert answer.status_code == 200, answer.text
    trace = answer.json()
    assert trace["open"] is False and trace["state"] == "succeeded"
    assert trace["link"] == f"app/#/runs/{run.id}/steps/w"
    types = [line["type"] for line in trace["lines"]]
    assert types[:3] == ["step.started", "step.progress", "consumption.reported"]
    assert types[-1] == "assignment.finished"
    assert "artifact.produced" in types and "step.boundary" in types
    assert [line["position"] for line in trace["lines"]] == list(range(1, len(types) + 1))
    texts = [line["text"] for line in trace["lines"]]
    assert "connecting with ***" in texts and "wrote the change" in texts
    assert "Started shell: plan" in texts and "Finished succeeded" in texts
    assert SECRET not in answer.text, "a secret value the instance holds is masked"

    later = await http.get(
        f"{base}/levels/runs/{run.id}/steps/w/trace?after=2", headers=bearer(owner)
    )
    assert later.json()["lines"][0]["position"] == 3
    assert later.json()["after"] == trace["after"] == len(types)

    ledger = await http.get(f"{base}/runs/{run.id}/ledger", headers=bearer(owner))
    entries = json.dumps(ledger.json()["entries"])
    for said in ("connecting", "wrote the change", SECRET, "+ one line"):
        assert said not in entries, f"the ledger holds no content: {said!r}"


async def test_the_trace_is_shown_to_the_owner_and_a_role_it_is_shared_with_and_nobody_else(
    client: Client,
) -> None:
    http, given, base = client
    run = await worked(given)
    owner = await key(given, "idn_ada", "owner")
    reviewer = await key(given, "idn_bob", "reviewer")
    nobody = await key(given, "idn_cyd")
    path = f"{base}/levels/runs/{run.id}/steps/w/trace"

    assert (await http.get(path, headers=bearer(reviewer))).status_code == 404
    assert (await http.get(path, headers=bearer(nobody))).status_code == 404
    assert (await http.get(path)).status_code == 401

    shared = await http.post(f"{path}/shares", json={"role": "reviewer"}, headers=bearer(owner))
    assert shared.status_code == 200, shared.text
    assert shared.json()["shared_with"] == ["reviewer"]
    assert shared.json()["link"] == f"app/#/runs/{run.id}/steps/w"
    assert (await http.get(path, headers=bearer(reviewer))).status_code == 200
    assert (await http.get(path, headers=bearer(nobody))).status_code == 404
    # Once the role reads it, it may hand it on to another role; a reader who may not see it
    # cannot share it.
    assert (
        await http.post(f"{path}/shares", json={"role": "audit"}, headers=bearer(nobody))
    ).status_code == 404

    withdrawn = await http.delete(f"{path}/shares/reviewer", headers=bearer(owner))
    assert withdrawn.status_code == 200 and withdrawn.json()["shared_with"] == []
    assert (await http.get(path, headers=bearer(reviewer))).status_code == 404

    async with given.persistence.transaction(TENANT):
        entries = await given.ledger.entries(TENANT, run.id)
    acts = [
        (e.kind, e.outcome, e.refs.actor, e.refs.step_id)
        for e in entries
        if e.kind.startswith("trace.")
    ]
    assert acts == [
        ("trace.shared", "reviewer", "idn_ada", "w"),
        ("trace.unshared", "reviewer", "idn_ada", "w"),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"role": "Ada Lovelace"},
        {"role": "idn_bob@example"},
        {"role": "reviewer", "identity": "idn_bob"},
    ],
)
async def test_a_share_names_a_role_never_a_person(client: Client, body: dict[str, Any]) -> None:
    http, given, base = client
    run = await worked(given)
    owner = await key(given, "idn_ada", "owner")
    answer = await http.post(
        f"{base}/levels/runs/{run.id}/steps/w/trace/shares", json=body, headers=bearer(owner)
    )
    assert answer.status_code == 422


async def test_a_trace_of_another_tenant_a_withheld_run_or_no_workers_step_is_none(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    http, given, base = client
    other = await worked(given, tenant=OTHER)
    await a_run(given, "run_rule")
    owner = await key(given, "idn_ada", "owner")
    for path in (f"levels/runs/{other.id}/steps/w/trace", "levels/runs/run_rule/steps/a/trace"):
        answer = await http.get(f"{base}/{path}", headers=bearer(owner))
        assert answer.status_code == 404 and OTHER not in answer.text

    run = await worked(given)
    original = visibility.may_see

    def withheld(reader: Reader, ref: RunRef) -> bool:
        return original(reader, ref) and ref.id != run.id

    monkeypatch.setattr(visibility, "may_see", withheld)
    path = f"{base}/levels/runs/{run.id}/steps/w/trace"
    assert (await http.get(path, headers=bearer(owner))).status_code == 404
    shared = await http.post(f"{path}/shares", json={"role": "reviewer"}, headers=bearer(owner))
    assert shared.status_code == 404


async def test_an_event_reaches_a_reader_who_asks_again_within_5_seconds(client: Client) -> None:
    http, given, base = client
    owner = await key(given, "idn_ada", "owner")
    reported: dict[int, float] = {}

    async def on_event(event: Event) -> None:
        reported[event.seq] = time.monotonic()

    worker = FakeWorker(
        script=tuple(InnerStep(f"s{n}", said=f"step {n}") for n in range(4)),
        inner_seconds=0.4,
        on_event=on_event,
    )
    running = asyncio.create_task(engine(given, worker).start(started()))
    seen: dict[int, float] = {}
    after = 0
    async with asyncio.timeout(30):
        while True:
            answer = await http.get(
                f"{base}/levels/runs/run_0001/steps/w/trace?after={after}", headers=bearer(owner)
            )
            if answer.status_code == 200:
                trace = answer.json()
                for line in trace["lines"]:
                    seen[line["position"]] = time.monotonic()
                after = trace["after"]
                if not trace["open"] and running.done():
                    break
            await asyncio.sleep(0.25)
    await running
    assert len(seen) == len(reported) > 8
    delays = [seen[position] - reported[position] for position in seen]
    assert max(delays) < 5.0, f"the slowest event took {max(delays):.2f} s"
