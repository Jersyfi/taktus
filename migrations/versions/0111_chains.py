"""A chain of processes stored by the instance, and every run of it (ADR-0301, UC-15.4).

Revision: 0111
Revises: 0109

What this adds, each one row per record as a document beside the tenant, its identifier and
the moment it was set:

- `declared_chain`, a chain as the tenant declared it, under the chain's identifier: a new
  declaration replaces the row;
- `chain_run`, one row per run of a chain, with the chain it started with, the link it stands
  at, the run of every link and the digest of every handover; its state moves on, a row is
  never deleted.

The tables start empty. Tenant and row-level security as on every other table (ADR-0020). The
previous release neither reads nor writes them (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0111"
down_revision = "0109"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = {
    "declared_chain": "SELECT, INSERT, UPDATE",
    "chain_run": "SELECT, INSERT, UPDATE",
}


def upgrade() -> None:
    for table, grants in TABLES.items():
        op.create_table(
            table,
            sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("id", sa.Text, nullable=False),
            sa.Column("at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("document", JSONB, nullable=False),
            sa.PrimaryKeyConstraint("tenant", "id"),
        )
        # The role, the grants and the table names are constants of this file, not input.
        op.execute(f"GRANT {grants} ON {table} TO {ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
        )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    for table in TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        op.drop_table(table)
