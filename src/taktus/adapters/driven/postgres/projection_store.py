"""The projection store over PostgreSQL: `ledger_projection`, one row per tenant and name."""

from __future__ import annotations

from sqlalchemy import BigInteger, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert

from taktus.adapters.driven.postgres import _schema as s
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.ports.persistence import Projected, Tenant


class PostgresProjectionStore:
    """The projection store port over `ledger_projection` (ADR-0105).

    A write without `replace` never waits. It first tries the projection's claim, a transaction
    advisory lock; when another transaction holds it, that transaction is storing a value of its
    own, and this one stores nothing. Holding the claim, it stores its value only when that value
    read further into the ledger than the stored one. Either way the value the caller computed is
    correct for the sequence number it read to, so nothing is lost by not storing it. A write
    with `replace` waits for the claim and stores its value whatever was stored."""

    def __init__(self, persistence: PostgresPersistence) -> None:
        self._persistence = persistence

    async def read(self, tenant: Tenant, name: str) -> Projected | None:
        connection = self._persistence.connection(tenant)
        row = (
            await connection.execute(
                select(s.ledger_projection.c.seq, s.ledger_projection.c.state).where(
                    (s.ledger_projection.c.tenant == tenant) & (s.ledger_projection.c.name == name)
                )
            )
        ).first()
        return None if row is None else Projected(seq=int(row.seq), state=row.state)

    async def write(
        self, tenant: Tenant, name: str, value: Projected, *, replace: bool = False
    ) -> bool:
        connection = self._persistence.connection(tenant)
        owner = select(s.tenant.c.lock_key).where(s.tenant.c.id == tenant).scalar_subquery()
        high = func.cast(owner, BigInteger) * literal_column("4294967296::bigint")
        low = func.hashtext(name).op("&")(literal_column("x'FFFFFFFF'::bigint"))
        key = high + low
        if replace:
            await connection.execute(select(func.pg_advisory_xact_lock(key)))
        elif not await connection.scalar(select(func.pg_try_advisory_xact_lock(key))):
            return False
        statement = insert(s.ledger_projection).values(
            tenant=tenant, name=name, seq=value.seq, state=value.state
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[s.ledger_projection.c.tenant, s.ledger_projection.c.name],
            set_={"seq": statement.excluded.seq, "state": statement.excluded.state},
            where=None if replace else s.ledger_projection.c.seq < statement.excluded.seq,
        )
        stored = await connection.execute(upsert.returning(s.ledger_projection.c.seq))
        return stored.first() is not None
