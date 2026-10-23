"""A change held to its evaluation cases, and drift measured on the same cases (ADR-0134,
UC-4.18).

Revision: 0069
Revises: 0068

What this adds: `process_version.evaluation`, nullable: the cases, the scorers and the schedule
the version declares under `evaluation`. Every version stored before has none, which is what it
declared: no version could declare one before this release.

And two tables, each starting empty: `evaluation`, one row per evaluation of a process on its
cases, as a document; and `corrected_case`, one row per case proposed from a person's
correction, as a document. Tenant and row-level security as on every other table (ADR-0020);
the application role may read and write them.

The previous release neither reads nor writes the column nor the tables (ADR-0093). It reads a
version by the columns it names, so a version this release stores with an evaluation is read
there without it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = (("evaluation", "started_at"), ("corrected_case", "proposed_at"))


def upgrade() -> None:
    op.add_column("process_version", sa.Column("evaluation", JSONB, nullable=True))
    for table, at in TABLES:
        op.create_table(
            table,
            sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("id", sa.Text, nullable=False),
            sa.Column("process_id", sa.Text, nullable=False),
            sa.Column("state", sa.Text, nullable=False),
            sa.Column(at, sa.DateTime(timezone=True), nullable=False),
            sa.Column(table, JSONB, nullable=False),
            sa.PrimaryKeyConstraint("tenant", "id"),
        )
        op.create_index(f"{table}_process", table, ["tenant", "process_id"])
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
    for table, _ in reversed(TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        op.drop_index(f"{table}_process", table_name=table)
        op.drop_table(table)
    op.drop_column("process_version", "evaluation")
