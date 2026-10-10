"""The run level of a real run, over HTTP from a daemon (UC-6.10 §2 *every level exists*, the
run's part; ADR-0063, issue #105).

A process is registered, a run started and its steps completed by the runner; the run level is
read over HTTP with an account key and holds every step with the vocabulary's glyphs, the states
the run recorded, and the run's own figures as the read API gives the run. A second run waits for
a person, and its level says on what, with nothing moving. A key of no identity is refused.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from taktus.components.reporting.domain.service.drawing import Glyph, Run, Step, check
from taktus.components.run.domain.model import Run as RunRecord
from taktus.components.run.domain.model import RunState
from taktus.shared.v1 import ConsumptionQuantities

from .test_daemon_scaling import Instance, instances, submit
from .test_live_changes import bundle, chosen, reader_key

__all__ = ["chosen", "instances"]


def flat(quantities: ConsumptionQuantities) -> dict[str, Any]:
    """The run's own quantities, named as the record names them."""
    found: dict[str, Any] = {}
    for name, value in quantities.quantities().items():
        if name == "currency":
            found.update({f"currency.{c}": v for c, v in value.items()})
        elif name == "tokens_by_model":
            for model, kinds in value.items():
                found.update(
                    {f"tokens_by_model.{model}.{k}": n for k, n in kinds.document().items()}
                )
        elif name == "compute_seconds":
            found[f"compute_seconds.{quantities.resource_class}"] = value
        else:
            found[name] = value
    return found


def drawn(level: dict[str, Any], key: str) -> list[tuple[Step | Run, Glyph]]:
    elements: list[tuple[Step | Run, Glyph]] = [
        (
            Run(name=level["run"]["id"], state=level["run"]["state"]),
            Glyph.model_validate(level["run"]["drawn"][key]),
        )
    ]
    elements.extend(
        (
            Step(name=s["id"], method=s["method"], exactness=s.get("exactness"), state=s["state"]),
            Glyph.model_validate(s["drawn"][key]),
        )
        for s in level["steps"]
    )
    return elements


async def test_a_registered_process_s_run_is_found_at_the_run_level(
    instances: Callable[..., Instance], chosen: str
) -> None:
    async with instances("level", TAKTUS_ROLES="api,runner", TAKTUS_TENANTS=chosen) as one:
        assert one.wired is not None
        wired = one.wired
        key = await reader_key(wired, chosen)
        done = await submit(wired, bundle(1, name="level"), tenant=chosen)
        waiting = await submit(wired, bundle(2, level=2, name="level"), tenant=chosen)

        async def state(run_id: str) -> RunState:
            async with wired.work.transaction(chosen):
                found = await wired.runs.get(chosen, run_id)
            assert found is not None
            return found.state

        async def settled() -> bool:
            return (await state(done.id)) is RunState.FINISHED and (
                await state(waiting.id)
            ) is RunState.WAITING_HUMAN

        async with asyncio.timeout(30):
            while not await settled():  # noqa: ASYNC110 — polling another task's state
                await asyncio.sleep(0.1)

        base = f"http://127.0.0.1:{one.settings.http_port}"
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(base_url=base, timeout=10) as http:
            answer = await http.get(f"/levels/runs/{done.id}", headers=headers)
            assert answer.status_code == 200, answer.text
            level = answer.json()
            assert level["run"]["state"] == "finished"
            assert [s["id"] for s in level["steps"]] == ["one", "two"]
            assert {s["state"] for s in level["steps"]} == {"succeeded"}
            assert level["steps"][1]["depends_on"] == ["one"]
            assert check(drawn(level, "moving"), motion=True) == ()
            assert check(drawn(level, "still"), motion=False) == ()
            assert all(s["drawn"]["moving"]["motion"] == "none" for s in level["steps"])

            record = RunRecord.model_validate(
                (await http.get(f"/runs/{done.id}?tenant={chosen}")).json()
            )
            shown = {f["name"]: f["value"] for f in level["run"].get("consumed", [])}
            assert shown == flat(record.consumed())

            held = (await http.get(f"/levels/runs/{waiting.id}", headers=headers)).json()
            first = held["steps"][0]
            assert first["state"] == "waiting_human"
            assert first["wait"]["account"] == "wait.human"
            assert "waits on a person" in first["text"]
            assert all(s["drawn"]["moving"]["motion"] == "none" for s in held["steps"])

            refused = await http.get(
                f"/levels/runs/{done.id}", headers={"Authorization": "Bearer tk_none"}
            )
            assert refused.status_code == 401
        await wired.engine.request_stop(waiting.id, chosen)
