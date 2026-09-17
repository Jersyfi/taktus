"""Provenance: one immutable record per completed step (ADR-0021).

Revision: 0002
Revises: 0001

What this creates, and why it looks the way it does:

- **`provenance`**, one row per step run that finished with a result. The row holds
  identifiers, tokens and digests: the run and step, the process version, the method and
  exactness class, the model and prompt version, the adapter and its version, the inputs as a
  JSON array of references with the moment each was read, the artifact identifiers produced,
  the digest of the value produced, and the sequence number of the ledger entry that recorded
  the step's completion. No content, no text (ADR-0021 §3).
- **Written once.** `(tenant, run_id, step_id)` is unique: a completed step has exactly one
  record. The application role may read and insert, nothing else, and a trigger rejects
  `UPDATE`, `DELETE` and `TRUNCATE` for every role that is not a superuser — the same two
  fences the ledger has (revision 0001). A record that could be edited would let a result
  defect rewrite its own history.
- **No foreign key.** The record outlives what it describes: a run's rows may one day be
  archived, the record stays. And the ledger entry it names belongs to another component
  (ADR-0016). The link is the sequence number, checked by the run component, not by the
  database.
- **Tenant and row-level security** as on every table (ADR-0020): the row carries its tenant,
  the policy `tenant_isolation` is forced.
- **Reading the chain.** `(tenant, run_id)` is indexed for the records of a run and for the
  first step of a chain walk; the walk itself is a recursive query over `inputs`
  (`src/taktus/adapters/driven/postgres/provenance_store.py`).
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "provenance"


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("process_version", sa.Text, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("exactness", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("prompt", sa.Text),
        sa.Column("adapter", sa.Text),
        sa.Column("adapter_version", sa.Text),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("outputs", JSONB, nullable=False),
        sa.Column("result_digest", sa.Text),
        sa.Column("ledger_seq", sa.BigInteger, nullable=False),
        _at("recorded_at"),
        sa.PrimaryKeyConstraint("tenant", "id"),
        sa.UniqueConstraint("tenant", "run_id", "step_id", name="provenance_once_per_step_run"),
    )
    op.create_index("provenance_run", TABLE, ["tenant", "run_id"])
    op.execute(
        f"""
        CREATE FUNCTION {TABLE}_is_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '{TABLE} is written once: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {TABLE}_immutable
        BEFORE UPDATE OR DELETE ON {TABLE}
        FOR EACH ROW EXECUTE FUNCTION {TABLE}_is_immutable()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {TABLE}_no_truncate
        BEFORE TRUNCATE ON {TABLE}
        FOR EACH STATEMENT EXECUTE FUNCTION {TABLE}_is_immutable()
        """
    )
    # The role and the table name are constants of this file, not input.
    op.execute(f"GRANT SELECT, INSERT ON {TABLE} TO {ROLE}")
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {TABLE} "
        f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
    )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.execute(f"DROP POLICY tenant_isolation ON {TABLE}")
    op.execute(f"REVOKE ALL ON {TABLE} FROM {ROLE}")
    op.execute(f"DROP TRIGGER {TABLE}_no_truncate ON {TABLE}")
    op.execute(f"DROP TRIGGER {TABLE}_immutable ON {TABLE}")
    op.execute(f"DROP FUNCTION {TABLE}_is_immutable()")
    op.drop_index("provenance_run", table_name=TABLE)
    op.drop_table(TABLE)
