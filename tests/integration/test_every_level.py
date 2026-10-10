"""Every level of UC-6.10 exists (§2 *every level exists*; ADR-0068, issue #192).

A process is registered on a daemon, a run of it started, and its steps completed with a result.
Over HTTP, with one account key, the reader finds the overview with the process, the process
graph, the run, and the origin of the result — the path back to the step that produced it,
drawn from the provenance record the run left.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from taktus.components.run.domain.model import RunState

from .test_daemon_scaling import Instance, instances, submit
from .test_live_changes import bundle, chosen, reader_key

__all__ = ["chosen", "instances"]


async def test_a_completed_step_is_found_at_all_four_levels(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with instances("levels", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        wired = one.wired
        key = await reader_key(wired, chosen)
        document = bundle(1, name="levels")
        process_id = document["id"]
        run = await submit(wired, document, tenant=chosen)

        async def finished() -> bool:
            async with wired.work.transaction(chosen):
                found = await wired.runs.get(chosen, run.id)
            return found is not None and found.state is RunState.FINISHED

        async with asyncio.timeout(30):
            while not await finished():  # noqa: ASYNC110 — polling the runner's progress
                await asyncio.sleep(0.1)

        base = f"http://127.0.0.1:{one.settings.http_port}"
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(base_url=base, timeout=10) as http:
            overview = (await http.get("/levels/overview", headers=headers)).json()
            [area] = overview["areas"]
            assert process_id in {p["id"] for p in area["processes"]}

            process = (await http.get(f"/levels/processes/{process_id}", headers=headers)).json()
            assert [s["id"] for s in process["steps"]] == ["one", "two"]
            assert run.id in {r["id"] for r in process["runs"]}

            level = (await http.get(f"/levels/runs/{run.id}", headers=headers)).json()
            assert {s["state"] for s in level["steps"]} == {"succeeded"}

            answer = await http.get(f"/levels/origins/{run.id}/two", headers=headers)
            assert answer.status_code == 200, answer.text
            origin = answer.json()
            assert origin["result"]["exactness"] == "exact"
            assert origin["result"]["depends_on"] == [f"{run.id}/two"]
            assert origin["steps"][0]["method"] == "rule"
            assert origin["steps"][0]["process_version"].startswith(f"{process_id}@")
