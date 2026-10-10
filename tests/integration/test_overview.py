"""The overview of a real tenant, over HTTP from a daemon (UC-6.10 §2, the overview's part;
ADR-0067, issue #191).

A process is registered and a run of it started; while it works, the overview counts it as
working, with the step it is running. When it ends, the change reaches a reader following the
tenant's stream within 5 seconds, and the overview read after it shows the process idle — the
figure the read API's runs give by the run component's own definition.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from taktus.components.run.domain.model import WORKING, Run

from .test_daemon_scaling import Instance, instances, submit, until
from .test_live_changes import Reading, bundle, chosen, reader_key

__all__ = ["chosen", "instances"]


def with_a_pause(n: int) -> dict[str, Any]:
    """Two rules with a wait of a few seconds between them: long enough to be seen working."""
    document = bundle(n, name="overview")
    document["steps"].insert(
        1,
        {
            "id": "pause",
            "method": "wait",
            "reason": "stands in for an external system",
            "rejected": [],
            "depends_on": ["one"],
            "work": {"seconds": 3},
        },
    )
    document["steps"][2]["depends_on"] = ["pause"]
    return document


def busy(level: dict[str, Any], process_id: str) -> dict[str, Any]:
    [area] = level["areas"]
    found: dict[str, Any] = next(p for p in area["processes"] if p["id"] == process_id)
    return found


async def test_a_working_run_is_counted_and_its_end_shows_the_process_idle_within_5_seconds(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with instances("overview", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        wired = one.wired
        key = await reader_key(wired, chosen)
        document = with_a_pause(1)
        process_id = document["id"]
        base = f"http://127.0.0.1:{one.settings.http_port}"
        headers = {"Authorization": f"Bearer {key}"}
        async with (
            httpx.AsyncClient(base_url=base, timeout=10) as http,
            Reading(f"{base}/changes", key) as reading,
        ):
            started = await submit(wired, document, tenant=chosen)
            seen: dict[str, Any] = {}

            async def working() -> bool:
                level = (await http.get("/levels/overview", headers=headers)).json()
                seen.update(busy(level, process_id))
                return bool(seen["working"] == 1)

            async with asyncio.timeout(10):
                while not await working():  # noqa: ASYNC110 — polling the runner's progress
                    await asyncio.sleep(0.1)
            assert "1 run working" in seen["text"]

            await until(
                lambda: any(
                    c["kind"] == "run.finished" and c["run"] == started.id
                    for c in reading.changes()
                ),
                seconds=20,
            )
            assert not reading.late(), reading.late()
            after = busy((await http.get("/levels/overview", headers=headers)).json(), process_id)
            assert (after["working"], after["waiting"]) == (0, 0)
            assert after.get("running", []) == []

            listed = (await http.get("/runs", headers=headers)).json()["runs"]
            mine = [Run.model_validate(r) for r in listed if r["id"] == started.id]
            assert after["working"] == sum(r.state in WORKING for r in mine)
