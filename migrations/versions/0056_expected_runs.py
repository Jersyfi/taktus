"""An expected run that does not happen raises an incident (ADR-0107, UC-4.16).

Revision: 0056
Revises: 0055

What this adds:

- `process_version.expect`, when a run of the version is expected; null for every version
  registered before, which inherits its schedule triggers as before.
- `ledger_entry.duration_seconds`, how long a run took, on `run.ended`; null on every entry
  written before. Adding a column changes no row, so the append-only trigger has nothing to
  refuse, and no entry's hash changes: an absent field is not hashed.
- `ledger_entry_process`, an index that finds a process's entries of a kind by time.
- `incident`, one row per incident, as a document, and beside it the columns a list of the open
  ones is read by. A row is never deleted: its state moves on.
- `watch_configuration`, one row per tenant that set its grace period and empty share.

Both tables start empty. Tenant and row-level security as on every other table (ADR-0020); the
application role may read and write them. The previous release neither reads nor writes any of
it (ADR-0093).
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("incident", "watch_configuration")


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.add_column("process_version", sa.Column("expect", JSONB))
    op.add_column("ledger_entry", sa.Column("duration_seconds", sa.Float))
    op.create_index(
        "ledger_entry_process",
        "ledger_entry",
        ["tenant", sa.text("(split_part(refs ->> 'process_version', '@', 1))"), "kind", "ts"],
    )
    op.create_table(
        "incident",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("process_id", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        _at("raised_at"),
        sa.Column("incident", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("incident_state", "incident", ["tenant", "state"])
    op.create_table(
        "watch_configuration",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        _at("configured_at"),
        sa.Column("configuration", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    for table in TABLES:
        # The role and the table names are constants of this file, not input.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
        )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
    op.drop_table("watch_configuration")
    op.drop_index("incident_state", table_name="incident")
    op.drop_table("incident")
    op.drop_index("ledger_entry_process", table_name="ledger_entry")
    op.drop_column("ledger_entry", "duration_seconds")
    op.drop_column("process_version", "expect")
