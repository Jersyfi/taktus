"""Deadlines and response limits are rules of the process (ADR-0133, UC-4.17).

Revision: 0068
Revises: 0067

What this adds:

- `process_version.deadlines`, nullable: the deadlines a version declares, by name. Every
  version stored before has none, which is what it declared: no version could declare one
  before this release.
- `run.deadlines`, nullable: the copy of its version's deadlines a run takes when it is
  created. Every run stored before has none.
- `deadline`, one row per deadline started for a run, never deleted. It starts empty.
- `working_time`, one row per tenant that set its working time. A tenant without a row holds the
  shipped default (NTC-0227). It starts empty.

Tenant and row-level security on both tables as on every other (ADR-0020); the application role
may read and write them. The previous release neither reads nor writes the columns nor the
tables (ADR-0093): it reads a version and a run by the columns it names.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("deadline", "working_time")


def upgrade() -> None:
    op.add_column("process_version", sa.Column("deadlines", JSONB, nullable=True))
    op.add_column("run", sa.Column("deadlines", JSONB, nullable=True))
    op.create_table(
        "deadline",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("deadline_state_due", "deadline", ["tenant", "state", "due_at"])
    op.create_table(
        "working_time",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("working_time", JSONB, nullable=False),
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
        op.drop_table(table)
    op.drop_column("run", "deadlines")
    op.drop_column("process_version", "deadlines")
