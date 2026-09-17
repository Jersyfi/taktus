"""Persistence over PostgreSQL — the one mandatory dependency (ADR-0002).

SQLAlchemy Core only; no ORM object exists here and none crosses into the domain
(`docs/architecture/project-structure.md` §4). Every transaction assumes the application role
and names its tenant, so that the row-level security of the schema (`migrations/`) applies to
every statement. The ledger and the provenance are append-only in the database itself. The
schema lives in `_schema.py` and is created by the migrations; the two are held together by a
test.
"""

from taktus.adapters.driven.postgres.ledger_store import PostgresLedgerStore
from taktus.adapters.driven.postgres.migrate import SchemaOutOfDate, check_schema, upgrade
from taktus.adapters.driven.postgres.persistence import PostgresPersistence
from taktus.adapters.driven.postgres.provenance_store import PostgresProvenanceStore
from taktus.adapters.driven.postgres.repository import PostgresRepository

__all__ = [
    "PostgresLedgerStore",
    "PostgresPersistence",
    "PostgresProvenanceStore",
    "PostgresRepository",
    "SchemaOutOfDate",
    "check_schema",
    "upgrade",
]
