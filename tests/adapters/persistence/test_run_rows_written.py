"""A commit writes the step that changed, not the whole run (#325).

Persisting a run deleted and wrote again every step run, checkpoint and artifact of the run on
every commit: 120 600 rows deleted over a 200-step run. The run's mapper now writes a child row
only where it is new or differs, and deletes one only where the document no longer holds it. The
database counts what a transaction wrote (`pg_stat_xact_user_tables`); these tests read it.
"""

from __future__ import annotations

import copy
import time
from typing import Any

import pytest
from sqlalchemy import text

from adapters.persistence import samples
from adapters.persistence.conftest import Backend
from taktus.adapters.driven.postgres import PostgresPersistence
from taktus.adapters.driven.postgres._mapping import MAPPERS

pytestmark = pytest.mark.usefixtures("postgres_url")

CHILDREN = ("step_run", "checkpoint", "artifact")
RUN = MAPPERS["run"]


@pytest.fixture
def postgres(postgres_backend: Backend) -> Backend:
    return postgres_backend


def _persistence(backend: Backend) -> PostgresPersistence:
    assert isinstance(backend.work, PostgresPersistence)
    return backend.work


async def _written(persistence: PostgresPersistence, tenant: str) -> int:
    """The rows of the run's children inserted, updated or deleted by this connection and not
    yet reported to the cumulative statistics. Those of an earlier transaction may still be
    among them, so a caller takes the difference across its own transaction."""
    rows = await persistence.connection(tenant).execute(
        text(
            "SELECT coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) "
            "FROM pg_stat_xact_user_tables WHERE relname = ANY(:tables)"
        ),
        {"tables": list(CHILDREN)},
    )
    return int(rows.scalar_one())


def _planned(template: dict[str, Any], index: int) -> dict[str, Any]:
    step = copy.deepcopy(template)
    step.update(step_id=f"s{index:03d}", index=index, method="rule", state="planned")
    for key in ("block", "checkpoint", "started_at", "finished_at"):
        step.pop(key, None)
    step["artifacts"] = []
    return step


def _run_of(steps: int, run_id: str, tenant: str) -> dict[str, Any]:
    """A run of `steps` rule steps, every one planned."""
    document = samples.run(run_id, tenant=tenant).document()
    template = document["step_runs"][2]
    document["step_runs"] = [_planned(template, index) for index in range(steps)]
    return document


def _succeed(document: dict[str, Any], index: int) -> None:
    """Step `index` succeeded with its result and its checkpoint, as the engine commits it."""
    step = document["step_runs"][index]
    at = "2026-09-16T12:00:02.123456Z"
    step.update(state="succeeded", started_at=at, finished_at=at)
    step["artifacts"] = [
        {"id": "result", "kind": "result", "digest": samples.DIGEST, "created_at": at}
    ]
    step["checkpoint"] = {
        "ref": f"ckpt/{document['id']}/{step['step_id']}",
        "step_id": step["step_id"],
        "taken_at": at,
        "artifact_ids": ["result"],
        "result_digest": samples.DIGEST,
    }


async def _commit(backend: Backend, tenant: str, document: dict[str, Any]) -> int:
    persistence = _persistence(backend)
    async with backend.work.transaction(tenant):
        before = await _written(persistence, tenant)
        await RUN.put(persistence.connection(tenant), tenant, document)
        return await _written(persistence, tenant) - before


async def _stored(backend: Backend, tenant: str, run_id: str) -> dict[str, Any] | None:
    persistence = _persistence(backend)
    async with backend.work.transaction(tenant):
        return await RUN.get(persistence.connection(tenant), tenant, run_id)


@pytest.mark.parametrize("steps", [20, 200])
async def test_a_commit_of_one_step_writes_a_constant_number_of_rows(
    postgres: Backend, steps: int
) -> None:
    tenant = await postgres.tenant()
    document = _run_of(steps, f"run_rows_{steps}", tenant)
    assert await _commit(postgres, tenant, document) == steps  # the first commit: every step

    begun = time.perf_counter()
    for index in range(steps):
        _succeed(document, index)
        # The step's row updated, its checkpoint and its result inserted: three, whatever the
        # run's length. Before #325 it was every row of the run, deleted and inserted again.
        assert await _commit(postgres, tenant, document) == 3, f"step {index}"
    elapsed = time.perf_counter() - begun
    print(f"{steps} steps committed one by one in {elapsed:.2f} s")

    assert await _commit(postgres, tenant, document) == 0  # nothing changed, nothing written


async def test_the_stored_run_equals_the_same_document_written_from_nothing(
    postgres: Backend,
) -> None:
    """Every kind of change a commit can carry — a new step, a new or changed artifact, a
    reordered one, an artifact or a checkpoint gone, a step run gone — leaves what writing the
    whole document into an empty run, as every commit did before, would have left."""
    tenant = await postgres.tenant()
    document = samples.run("run_same", tenant=tenant).document()
    changes = [
        lambda d: None,
        lambda d: _succeed(d, 2),
        lambda d: d["step_runs"][1]["artifacts"].append(
            {"id": "output-2", "kind": "log", "digest": samples.DIGEST}
        ),
        lambda d: d["step_runs"][1]["artifacts"].reverse(),
        lambda d: d["step_runs"][1]["artifacts"][0].update(title="renamed", size_bytes=4),
        lambda d: d["step_runs"][1]["artifacts"].pop(),
        lambda d: d["step_runs"][1].pop("checkpoint"),
        lambda d: d["step_runs"][0]["checkpoint"].update(artifact_ids=[]),
        lambda d: d["step_runs"].append(_planned(d["step_runs"][-1], len(d["step_runs"]))),
        lambda d: d["step_runs"].pop(),
    ]
    for number, change in enumerate(changes):
        change(document)
        await _commit(postgres, tenant, document)
        fresh = copy.deepcopy(document)
        fresh["id"] = f"run_fresh_{number}"
        await _commit(postgres, tenant, fresh)

        stored = await _stored(postgres, tenant, "run_same")
        from_nothing = await _stored(postgres, tenant, fresh["id"])
        assert stored is not None and from_nothing is not None
        from_nothing["id"] = "run_same"
        assert stored == from_nothing, f"after change {number}"
