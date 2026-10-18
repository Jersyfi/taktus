"""A read of the ledger costs what it returns (ADR-0105).

Revision: 0054
Revises: 0053

What this adds: `ledger_projection`, one row per tenant and name, holding a value derived from
the tenant's ledger and the sequence number of the last entry it read. The projections and the
checkpoint of the chain's verification live there. Every row can be rebuilt from the ledger, so
the table starts empty and fills on first read. Beside it, the index `ledger_entry_kind`, which
reads a tenant's entries of one kind in sequence order without the others. Tenant and row-level
security as on every other table (ADR-0020). The application role may read, insert and update a
projection, and may not delete one. The previous release neither reads nor writes either.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "ledger_projection"


def upgrade() -> None:
    op.create_index("ledger_entry_kind", "ledger_entry", ["tenant", "kind", "seq"])
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "name"),
    )
    # The role and the table name are constants of this file, not input.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {ROLE}")
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {TABLE} "
        f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
    )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9). What it drops is derived
    # from the ledger and is rebuilt from it.
    op.execute(f"DROP POLICY tenant_isolation ON {TABLE}")
    op.execute(f"REVOKE ALL ON {TABLE} FROM {ROLE}")
    op.drop_table(TABLE)
    op.drop_index("ledger_entry_kind", table_name="ledger_entry")
