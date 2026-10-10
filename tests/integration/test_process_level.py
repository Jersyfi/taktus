"""The process level of a real process, over HTTP from a daemon (UC-6.10 §2, the process's part;
ADR-0064, issue #190).

A process is registered and its graph read with its autonomy statement. A run of it is started
while a reader follows the process's stream: its changes arrive within the 5 seconds of UC-6.10,
and the level read after them lists the run. A new version of the process is registered, and the
graph has changed with nothing else edited; the earlier version is still read by name.
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable

import httpx

from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
)
from taktus.components.reporting.domain.service.drawing import Glyph, Step, check
from taktus.components.run.domain.model import RunState

from .test_daemon_scaling import Instance, instances, submit, until
from .test_live_changes import Reading, bundle, chosen, reader_key

__all__ = ["chosen", "instances"]


def drawn(level: dict[str, object], key: str) -> list[tuple[Step, Glyph]]:
    steps = level["steps"]
    assert isinstance(steps, list)
    return [
        (
            Step(
                name=s["id"],
                method=s["method"],
                exactness=s.get("exactness"),
                state="running" if s.get("running_in") else "planned",
            ),
            Glyph.model_validate(s["drawn"][key]),
        )
        for s in steps
    ]


async def test_a_registered_process_is_found_at_the_process_level_and_moves_with_its_runs(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with instances("process", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        wired = one.wired
        key = await reader_key(wired, chosen)
        document = bundle(1, name="graph")
        process_id = document["id"]
        await wired.register_version.execute(RegisterProcessVersion(document, tenant=chosen))

        base = f"http://127.0.0.1:{one.settings.http_port}"
        headers = {"Authorization": f"Bearer {key}"}
        path = f"/levels/processes/{process_id}"
        async with httpx.AsyncClient(base_url=base, timeout=10) as http:
            first = (await http.get(path, headers=headers)).json()
            assert first["process"]["autonomy"]["level"] == 3
            assert "Runs at autonomy level 3" in first["process"]["autonomy_text"]
            assert [s["id"] for s in first["steps"]] == ["one", "two"]
            assert first.get("runs", []) == []
            assert check(drawn(first, "moving"), motion=True) == ()
            assert check(drawn(first, "still"), motion=False) == ()

            stream = f"{base}/changes?process={process_id}"
            async with Reading(stream, key) as reading:
                started = await submit(wired, document, tenant=chosen)

                async def finished() -> bool:
                    async with wired.work.transaction(chosen):
                        run = await wired.runs.get(chosen, started.id)
                    return run is not None and run.state is RunState.FINISHED

                async with asyncio.timeout(30):
                    while not await finished():  # noqa: ASYNC110 — polling the runner's state
                        await asyncio.sleep(0.1)
                await until(lambda: "run.finished" in {c["kind"] for c in reading.changes()})
                assert not reading.late(), reading.late()
                assert {c["run"] for c in reading.changes()} == {started.id}

            after = (await http.get(path, headers=headers)).json()
            assert [r["id"] for r in after["runs"]] == [started.id]
            assert after["runs"][0]["state"] == "finished"
            assert all(s["drawn"]["moving"]["motion"] == "none" for s in after["steps"])

            changed = copy.deepcopy(document)
            changed["version"] = "2"
            changed["steps"].append(
                {
                    "id": "three",
                    "method": "rule",
                    "reason": "r",
                    "rejected": [],
                    "exactness": "exact",
                    "depends_on": ["two"],
                    "work": {"rule": "constant", "value": {"k": 1}},
                }
            )
            await wired.register_version.execute(RegisterProcessVersion(changed, tenant=chosen))
            newer = (await http.get(path, headers=headers)).json()
            assert newer["process"]["version"] == "2"
            assert [s["id"] for s in newer["steps"]] == ["one", "two", "three"]
            assert newer.get("runs", []) == [], "the runs of version 1 are not version 2's"
            earlier = (
                await http.get(
                    path, params={"version": first["process"]["version"]}, headers=headers
                )
            ).json()
            assert [s["id"] for s in earlier["steps"]] == ["one", "two"]
            assert [r["id"] for r in earlier["runs"]] == [started.id]

            refused = await http.get(path, headers={"Authorization": "Bearer tk_none"})
            assert refused.status_code == 401
