"""The provenance store keeps one record per step run, written once, and walks the chain
behind an artifact — the same against the memory adapter and against PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adapters.persistence.conftest import Backend
from taktus.ports.persistence import DuplicateProvenance, SpoiltTransaction
from taktus.shared.v1 import InputKind, Provenance, ProvenanceInput

AT = datetime(2026, 9, 16, 12, 0, 0, 123456, tzinfo=UTC)


def digest(n: int) -> str:
    return "sha256:" + f"{n:02x}" * 32


def record(
    id: str,
    run_id: str,
    step_id: str,
    seq: int,
    *,
    outputs: tuple[str, ...] = (),
    reads: tuple[tuple[str, str, str | None], ...] = (),
    result: int | None = None,
    **fields: object,
) -> Provenance:
    inputs = tuple(
        ProvenanceInput(
            kind=InputKind.RESULT if artifact is None else InputKind.ARTIFACT,
            run_id=run,
            step_id=step,
            artifact_id=artifact,
            digest=digest(seq),
            observed_at=AT,
        )
        for run, step, artifact in reads
    )
    return Provenance.model_validate(
        {
            "id": id,
            "run_id": run_id,
            "step_id": step_id,
            "process_version": "p@1",
            "method": "rule",
            "exactness": "exact",
            "inputs": [i.document() for i in inputs],
            "outputs": list(outputs),
            "result_digest": None if result is None else digest(result),
            "ledger_seq": seq,
            "recorded_at": AT,
            **fields,
        }
    )


async def test_records_come_back_per_run_in_ledger_order_with_every_field(
    backend: Backend,
) -> None:
    tenant = await backend.tenant()
    store = backend.provenance_store
    full = record(
        "prov_2",
        "r1",
        "b",
        7,
        outputs=("x", "y"),
        reads=(("r1", "a", None), ("r0", "z", "art")),
        result=9,
        method="ml",
        exactness="sourced",
        model="clf@1.2",
        prompt="extract@3",
        adapter="worker.http",
        adapter_version="1.1.0",
    )
    first = record("prov_1", "r1", "a", 3, outputs=("result",), result=1)
    other = record("prov_0", "r0", "z", 1, outputs=("art",))
    async with backend.work.transaction(tenant):
        await store.append(tenant, full)
        await store.append(tenant, first)
        await store.append(tenant, other)
    async with backend.work.transaction(tenant):
        of_run = await store.of_run(tenant, "r1")
        assert [r.id for r in of_run] == ["prov_1", "prov_2"], "ledger order"
        assert of_run[1] == full and of_run[1].document() == full.document()
        assert await store.of_run(tenant, "nope") == []


async def test_a_step_run_is_recorded_once(backend: Backend) -> None:
    tenant = await backend.tenant()
    store = backend.provenance_store
    async with backend.work.transaction(tenant):
        await store.append(tenant, record("prov_1", "r1", "a", 3))
    with pytest.raises(DuplicateProvenance):
        async with backend.work.transaction(tenant):
            await store.append(tenant, record("prov_other", "r1", "a", 9))
    # Caught inside the block: the transaction is spoilt all the same.
    with pytest.raises(SpoiltTransaction):
        async with backend.work.transaction(tenant):
            await store.append(tenant, record("prov_2", "r1", "b", 6))
            with pytest.raises(DuplicateProvenance):
                await store.append(tenant, record("prov_3", "r1", "a", 12))
    async with backend.work.transaction(tenant):
        assert [r.id for r in await store.of_run(tenant, "r1")] == ["prov_1"], (
            "the spoilt block left nothing"
        )


async def test_one_chain_per_tenant(backend: Backend) -> None:
    a, b = await backend.tenant(), await backend.tenant()
    store = backend.provenance_store
    async with backend.work.transaction(a):
        await store.append(a, record("prov_1", "r1", "a", 3, outputs=("x",)))
    async with backend.work.transaction(b):
        assert await store.of_run(b, "r1") == []
        assert await store.chain(b, "r1", "x") == []
        await store.append(
            b, record("prov_1", "r1", "a", 3, outputs=("x",))
        )  # same ids, other tenant
    async with backend.work.transaction(a):
        assert [r.id for r in await store.chain(a, "r1", "x")] == ["prov_1"]


async def test_the_chain_behind_an_artifact_walks_back_across_runs_in_one_query(
    backend: Backend,
) -> None:
    """r0 produced `source`; r1 read it into `a`, computed `b` from `a`'s value, and `c`
    from `b` and `a`; `d` read nothing the artifact depends on. The chain behind `c`'s
    artifact is c, b, a, source — each once, although `a` is reached twice."""
    tenant = await backend.tenant()
    store = backend.provenance_store
    async with backend.work.transaction(tenant):
        await store.append(tenant, record("prov_0", "r0", "fetch", 2, outputs=("source",)))
        await store.append(
            tenant,
            record(
                "prov_1",
                "r1",
                "a",
                10,
                outputs=("a-out",),
                result=1,
                reads=(("r0", "fetch", "source"),),
            ),
        )
        await store.append(
            tenant, record("prov_2", "r1", "b", 13, result=2, reads=(("r1", "a", None),))
        )
        await store.append(
            tenant,
            record(
                "prov_3",
                "r1",
                "c",
                16,
                outputs=("final",),
                reads=(("r1", "b", None), ("r1", "a", "a-out")),
            ),
        )
        await store.append(tenant, record("prov_4", "r1", "d", 19, outputs=("aside",)))
    async with backend.work.transaction(tenant):
        walked = await store.chain(tenant, "r1", "final")
        assert [r.step_id for r in walked] == ["c", "b", "a", "fetch"]
        assert walked[-1].run_id == "r0", "the chain crosses into the earlier run"
        assert [r.step_id for r in await store.chain(tenant, "r1", "aside")] == ["d"]
        assert await store.chain(tenant, "r0", "final") == [], "the artifact is named per run"
        assert await store.chain(tenant, "r1", "nothing") == []
