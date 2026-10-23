"""The trace inside a step, kept outside the ledger for the tenant's retention (ADR-0135,
UC-6.14).

Revision: 0070
Revises: 0069

What this adds, three tables, each starting empty:

- `step_trace`, one row per event a worker reported in a step, its texts masked: the run, the
  step, the assignment and the event's `seq`, the line's position in the step's trace, and what
  the worker contract carries for the event, as a document. It is the one table whose rows the
  application deletes on its own: a line whose retention ended is erased.
- `step_trace_share`, one row per role a step's trace is shared with. A share withdrawn is
  deleted; the ledger keeps that it was made and withdrawn.
- `trace_retention`, one row per tenant that set how long its traces are kept. A tenant without
  one keeps them for the default.

Tenant and row-level security as on every other table (ADR-0020).

The previous release neither reads nor writes the tables (ADR-0093). A worker's events it read
were not kept, so a run it continues has no trace for what it read.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("step_trace", "step_trace_share", "trace_retention")


def _tenant() -> sa.Column[str]:
    return sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "step_trace",
        _tenant(),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("assignment_id", sa.Text, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("detail", JSONB, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant", "run_id", "step_id", "assignment_id", "seq"),
    )
    op.create_index(
        "step_trace_position", "step_trace", ["tenant", "run_id", "step_id", "position"]
    )
    op.create_index("step_trace_recorded", "step_trace", ["tenant", "recorded_at"])
    op.create_table(
        "step_trace_share",
        _tenant(),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "run_id", "step_id", "role"),
    )
    op.create_table(
        "trace_retention",
        _tenant(),
        sa.Column("days", sa.Integer, nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant"),
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
    op.drop_table("trace_retention")
    op.drop_table("step_trace_share")
    op.drop_index("step_trace_recorded", table_name="step_trace")
    op.drop_index("step_trace_position", table_name="step_trace")
    op.drop_table("step_trace")
