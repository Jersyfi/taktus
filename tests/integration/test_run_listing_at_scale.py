"""Listing runs at scale answers in time and never stalls the event loop (issue #310, ADR-0094).

A tenant holds 2 000 runs of ten steps each, every step with its artifact and its checkpoint.
A daemon serving the `api` role answers `GET /runs`, a page at a time, and
`GET /levels/overview` from them, in this process, on the event loop that also renews a
runner's lease. A ticker on the same loop measures the longest stall while each is answered.

Before the change, `GET /runs` took 56.9 s at this size and blocked the loop for 56 s
(docs/research/2026-10-12-devops-review.md §E4); this test measured 45 to 53 s for it, and 45 s
for the overview, each a stall of the same length. The bounds are the issue's: under 2 s, and no
stall over 0.5 s. Every page read in turn returns every run exactly once, newest first.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text

from taktus.adapters.driven.postgres import _schema as schema
from taktus.adapters.driving.rest.app import PAGE_MAXIMUM
from taktus.components.run.domain.model import Checkpoint, Run, RunState, StepState
from taktus.composition.daemon import Wired
from taktus.ports.worker import ComputeLimit, Limits
from taktus.shared.v1 import Artifact, ExactnessClass, Method, Rejected, Step

from .test_daemon_scaling import Instance, instances
from .test_live_changes import chosen, reader_key

__all__ = ["chosen", "instances"]

RUNS = 2_000
STEPS = 10
AT = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
DIGEST = "sha256:" + "ab" * 32
ANSWER_SECONDS = 2.0
STALL_SECONDS = 0.5


def template(tenant: str) -> Run:
    """A finished run of ten rule steps, each with its result and its checkpoint."""
    steps = tuple(
        Step(
            id=f"step-{n}",
            method=Method.RULE,
            reason="a fixed rule",
            rejected=(Rejected(method=Method.LLM, why="nothing here needs judgement"),),
            exactness=ExactnessClass.EXACT,
            depends_on=(f"step-{n - 1}",) if n else None,
        )
        for n in range(STEPS)
    )
    run = Run(
        id="run_0",
        plan_id="pln_0",
        process_version="listing@1",
        tenant=tenant,
        identity="idn_t",
        autonomy_level=3,
        budget=Limits(compute=ComputeLimit(seconds=2, resource_class="cpu.small")),
        steps=steps,
        work={},
        state=RunState.FINISHED,
        created_at=AT,
        updated_at=AT,
    )
    for n, step in enumerate(steps):
        at = AT + timedelta(seconds=n)
        ran = run.step_run(step.id).to(StepState.ADMITTED).to(StepState.RUNNING, started_at=at)
        ran = ran.to(
            StepState.SUCCEEDED,
            artifacts=(Artifact(id=f"result-{n}", kind="result", digest=DIGEST, created_at=at),),
            checkpoint=Checkpoint(
                ref=f"ckpt/run_0/{step.id}",
                step_id=step.id,
                taken_at=at,
                artifact_ids=(f"result-{n}",),
                result_digest=DIGEST,
            ),
            finished_at=at,
        )
        run = run.with_step_run(ran)
    return run


async def seed(wired: Wired, tenant: str) -> None:
    """One run through the repository, then 1 999 copies of its rows made by the database: each
    with its own id and a creation time one second later than the one before."""
    async with wired.work.transaction(tenant):
        await wired.runs.put(tenant, template(tenant))
    copied = {
        schema.run: {"id": "'run_' || n", "created_at": "created_at + n * interval '1 second'"},
        schema.step_run: {"run_id": "'run_' || n"},
        schema.checkpoint: {"run_id": "'run_' || n"},
        schema.artifact: {"run_id": "'run_' || n"},
    }
    async with wired.persistence.engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('taktus.tenant', :t, true)"), {"t": tenant}
        )
        for table, changed in copied.items():
            names = [c.name for c in table.columns]
            values = [changed.get(name, name) for name in names]
            key = "id" if table is schema.run else "run_id"
            await connection.execute(
                text(
                    f"INSERT INTO {table.name} ({', '.join(names)}) "  # noqa: S608 — names from the schema
                    f"SELECT {', '.join(values)} FROM {table.name}, "
                    f"generate_series(1, {RUNS - 1}) AS n "
                    f"WHERE tenant = :t AND {key} = 'run_0'"
                ),
                {"t": tenant},
            )


async def measured[T](call: Callable[[], Awaitable[T]]) -> tuple[T, float, float]:
    """The answer, the seconds it took, and the longest the event loop went without turning."""
    longest = 0.0
    done = asyncio.Event()

    async def tick() -> None:
        nonlocal longest
        last = time.perf_counter()
        while not done.is_set():
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            longest = max(longest, now - last - 0.01)
            last = now

    ticker = asyncio.create_task(tick())
    await asyncio.sleep(0)
    started = time.perf_counter()
    answer = await call()
    took = time.perf_counter() - started
    done.set()
    await ticker
    return answer, took, longest


async def test_two_thousand_runs_are_listed_in_time_without_stalling_the_loop(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with instances("listing", TAKTUS_ROLES="api", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        await seed(one.wired, chosen)
        key = await reader_key(one.wired, chosen)
        base = f"http://127.0.0.1:{one.settings.http_port}"
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(base_url=base, timeout=120) as http:

            async def get(path: str, **params: Any) -> httpx.Response:
                return await http.get(path, headers=headers, params=params)

            first, took, stall = await measured(lambda: get("/runs"))
            print(f"\nGET /runs, first page: {took:.3f} s, longest stall {stall:.3f} s")
            assert first.status_code == 200, first.text
            assert took < ANSWER_SECONDS and stall < STALL_SECONDS, (took, stall)

            overview, took, stall = await measured(lambda: get("/levels/overview"))
            print(f"GET /levels/overview: {took:.3f} s, longest stall {stall:.3f} s")
            assert overview.status_code == 200, overview.text
            assert took < ANSWER_SECONDS and stall < STALL_SECONDS, (took, stall)
            [area] = overview.json()["areas"]
            listing = next(p for p in area["processes"] if p["id"] == "listing")
            assert (listing["working"], listing["waiting"]) == (0, 0)

            seen: list[str] = []
            page = first.json()
            pages = 1
            longest_page = 0.0
            while True:
                seen.extend(r["id"] for r in page["runs"])
                if "next" not in page:
                    break
                answer, took, stall = await measured(
                    lambda cursor=page["next"]: get("/runs", after=cursor)
                )
                assert answer.status_code == 200, answer.text
                assert took < ANSWER_SECONDS and stall < STALL_SECONDS, (took, stall)
                longest_page = max(longest_page, took)
                page = answer.json()
                pages += 1
            print(f"every page, {pages} of them: the slowest {longest_page:.3f} s")
            assert seen == [f"run_{n}" for n in reversed(range(RUNS))], "each once, newest first"

            largest, took, stall = await measured(lambda: get("/runs", limit=PAGE_MAXIMUM))
            print(f"GET /runs?limit={PAGE_MAXIMUM}: {took:.3f} s, longest stall {stall:.3f} s")
            assert largest.status_code == 200 and len(largest.json()["runs"]) == PAGE_MAXIMUM
            assert took < ANSWER_SECONDS and stall < STALL_SECONDS, (took, stall)

        # Every other reader of the whole list, such as the stream's snapshot, reads it in time
        # proportional to its length, and the loop turns meanwhile. The time is printed, not
        # bounded: it grows with the tenant, which a page does not.
        async def every_run() -> int:
            async with wired.work.transaction(chosen):
                return len(await wired.runs.list(chosen))

        wired = one.wired
        counted, took, stall = await measured(every_run)
        print(f"every run through the repository: {took:.3f} s, longest stall {stall:.3f} s")
        assert counted == RUNS and stall < STALL_SECONDS, stall
