"""Views, reports, a person's own view, the value basis and discovered processes (ADR-0241,
ADR-0242, ADR-0244, ADR-0245).

Revision: 0102
Revises: 0101

What this adds, each one row per record as a document beside the tenant, its identifier and
the moment it was set:

- `view_configuration`, a tenant's views and entitlements (ADR-0241 §2);
- `report_definition`, a report's reader role, trigger and channel (ADR-0242 §1);
- `own_view`, a person's own view's settings, read for that person alone (ADR-0245 §1);
- `value_basis`, one row per version of a tenant's value basis, written once and never changed:
  the application role may read and insert rows, and neither update nor delete one (ADR-0244 §2);
- `discovered_process`, a process nobody wrote down, through its five stages (ADR-0245 §2).

The tables start empty. Tenant and row-level security as on every other table (ADR-0020). The
previous release neither reads nor writes them (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = {
    "view_configuration": "SELECT, INSERT, UPDATE",
    "report_definition": "SELECT, INSERT, UPDATE",
    "own_view": "SELECT, INSERT, UPDATE",
    "value_basis": "SELECT, INSERT",
    "discovered_process": "SELECT, INSERT, UPDATE",
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
