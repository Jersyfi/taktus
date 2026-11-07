"""Write grants on a connection, the knowledge index, and instantiated domains (UC-5.6,
UC-5.5, UC-15.1).

Revision: 0106
Revises: 0107

What this adds, three tables of one shape — tenant, id, the moment the row was written, and the
record as a document:

- `connection_grant`: one row per grant made on a connection, such as writing into the data
  warehouse (UC-5.6). A connection reads only until a person grants more; a grant is withdrawn
  by a later row, never by deleting one.
- `knowledge_entry`: one row per place of a connected source that Taktus read — its reference,
  its link, its digest and when it was read (UC-5.5). The source stays the record; the entry
  holds no copy of its content.
- `domain_instance`: one row per domain instantiated from a blueprint (UC-15.1): the blueprint
  and its version, the domain's named owner, the capabilities bound and the processes proposed.

Each starts empty. Tenant and row-level security as on every other table (ADR-0020); the
application role may read, insert and update them. The previous release neither reads nor
writes them (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0106"
down_revision = "0107"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("connection_grant", "knowledge_entry", "domain_instance")


def upgrade() -> None:
    for table in TABLES:
        op.create_table(
            table,
            sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("id", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("document", JSONB, nullable=False),
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
