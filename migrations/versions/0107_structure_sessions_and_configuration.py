"""The organisation's structure, sessions with a project's knowledge, and the configuration a
plan calls for (ADR-0275, ADR-0276, ADR-0277, ADR-0278).

Revision: 0107
Revises: 0106

What this adds, one row per record, the record as a document beside its tenant and identifier:

- `org_structure`: a tenant's named levels; `structure_unit`: a unit of its structure, a
  project among them; `placement`: one object in one unit; `filing`: where something Taktus set
  up is documented; `knowledge_home`: a unit's knowledge system.
- `project_session`: one participant's session in one project, with its turns and outcomes.
- `configuration_change`: one change a commissioned plan makes in a target system, with what
  undoing it requires.

All start empty. Tenant and row-level security as on every other table (ADR-0020); the
application role may read, insert and update them. A row is never deleted. The previous release
reads and writes none of these tables (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = {
    "org_structure": "structure",
    "structure_unit": "unit",
    "placement": "placement",
    "filing": "filing",
    "knowledge_home": "home",
    "project_session": "session",
    "configuration_change": "change",
}


def upgrade() -> None:
    for table, column in TABLES.items():
        op.create_table(
            table,
            sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("id", sa.Text, nullable=False),
            sa.Column(column, JSONB, nullable=False),
            sa.PrimaryKeyConstraint("tenant", "id"),
        )
        # The role and the table names are constants of this file, not input.
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {ROLE}")
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
        op.drop_table(table)
