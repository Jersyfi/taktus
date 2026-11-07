"""A limit per unit of the structure, inherited along it and watched for harm (ADR-0282,
UC-8.5, UC-8.10).

Revision: 0108
Revises: 0107

What this adds: `unit_limit`, one row per limit a tenant set for a unit of its structure,
under the limit's name; a limit taken away keeps its row, marked cleared. `limit_watch`, one
row per tenant that set its figures for a limit that does harm. Both start empty. And the
nullable column `run.org_path`: where a run is attributed in the structure when it is created.
A run created before this migration has none, and is attributed to its department alone.

Tenant and row-level security as on every other table (ADR-0020); the application role may read
and write them. The previous release neither reads nor writes the tables or the column
(ADR-0093): a run it creates has no path, and no unit limit holds a step it admits.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
LIMIT = "unit_limit"
WATCH = "limit_watch"


def _isolated(table: str) -> None:
    # The role and the table names are constants of this file, not input.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
    )


def upgrade() -> None:
    op.create_table(
        LIMIT,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("unit_limit", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    _isolated(LIMIT)
    op.create_table(
        WATCH,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("watch", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    _isolated(WATCH)
    op.add_column("run", sa.Column("org_path", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("run", "org_path")
    for table in (WATCH, LIMIT):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        op.drop_table(table)
