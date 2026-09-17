from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import DuplicateProvenance, Tenant
from taktus.shared.v1 import Provenance

# The chain behind one artifact, in one statement: the record of the run that lists the
# artifact among its outputs, then — recursively — every record an input names by run and
# step, across the tenant's runs. UNION rather than UNION ALL, so that a record reached on two
# paths appears once. Newest ledger entry first: the producer, then what it read, and so on
# back, which is also the order across runs, since a tenant has one ledger chain.
CHAIN = text(
    """
    WITH RECURSIVE walk AS (
        SELECT p.* FROM provenance p
        WHERE p.tenant = :tenant AND p.run_id = :run_id AND p.outputs ? :artifact_id
        UNION
        SELECT p.* FROM provenance p
        JOIN walk w ON p.tenant = w.tenant
        JOIN LATERAL jsonb_array_elements(w.inputs) AS i ON true
        WHERE p.run_id = i.value ->> 'run_id' AND p.step_id = i.value ->> 'step_id'
    )
    SELECT * FROM walk ORDER BY ledger_seq DESC
    """
)


class PostgresProvenanceStore:
    """The provenance store port over `provenance`. Written once, twice over: the application
    role may not update or delete, and a trigger rejects it for everyone but a superuser
    (`migrations/versions/0002_provenance.py`). One record per step run: the unique key
    `(tenant, run_id, step_id)` refuses a second."""

    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def append(self, tenant: Tenant, record: Provenance) -> None:
        connection = self._persistence.connection(tenant)
        document = record.document()
        statement = insert(s.provenance).values(
            tenant=tenant,
            id=record.id,
            run_id=record.run_id,
            step_id=record.step_id,
            process_version=record.process_version,
            method=document["method"],
            exactness=document.get("exactness"),
            model=document.get("model"),
            prompt=document.get("prompt"),
            adapter=document.get("adapter"),
            adapter_version=document.get("adapter_version"),
            inputs=document["inputs"],
            outputs=document["outputs"],
            result_digest=document.get("result_digest"),
            ledger_seq=record.ledger_seq,
            recorded_at=record.recorded_at,
        )
        try:
            await connection.execute(statement)
        except IntegrityError as error:
            # The unique key refused it. The transaction is spoilt from here; the unit of
            # work rolls it back when the error leaves the block.
            raise DuplicateProvenance(tenant, record.run_id, record.step_id) from error

    async def of_run(self, tenant: Tenant, run_id: str) -> Sequence[Provenance]:
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            select(s.provenance)
            .where(s.provenance.c.tenant == tenant, s.provenance.c.run_id == run_id)
            .order_by(s.provenance.c.ledger_seq)
        )
        return [_record(row) for row in rows]

    async def chain(self, tenant: Tenant, run_id: str, artifact_id: str) -> Sequence[Provenance]:
        connection = self._persistence.connection(tenant)
        rows = await connection.execute(
            CHAIN, {"tenant": tenant, "run_id": run_id, "artifact_id": artifact_id}
        )
        return [_record(row) for row in rows]


def _record(row: Row[Any]) -> Provenance:
    recorded_at: datetime = row.recorded_at
    document: dict[str, Any] = {
        "id": row.id,
        "run_id": row.run_id,
        "step_id": row.step_id,
        "process_version": row.process_version,
        "method": row.method,
        "inputs": row.inputs,
        "outputs": row.outputs,
        "ledger_seq": row.ledger_seq,
        "recorded_at": recorded_at,
    }
    for name in ("exactness", "model", "prompt", "adapter", "adapter_version", "result_digest"):
        value = getattr(row, name)
        if value is not None:
            document[name] = value
    return Provenance.model_validate(document)
