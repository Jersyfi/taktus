"""A person's pause or cancellation of a run, plans worked out in dialogue, and the automation
coach (ADR-0236, ADR-0237, ADR-0240).

Revision: 0101
Revises: 0100

What this adds: `run_steering`, one row per run a person asked to pause or to cancel — the
request asked last, with its kind and state — which the runner holding the run reads at each
step boundary; and `plan_draft`, one row per plan worked out in dialogue, at its current
version; `coach_settings`, `coach_hint` and `coach_policy`, a person's coach, the hints it
offered them, and a tenant's period after which an automation counts as lasting. All start
empty. Tenant and row-level security as on every other table (ADR-0020);
the application role may read, insert and update them. A row is never deleted.

The previous release reads and writes none of these tables (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("run_steering", "plan_draft", "coach_settings", "coach_hint", "coach_policy")


def upgrade() -> None:
    op.create_table(
        "run_steering",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("steering", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "plan_draft",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("draft", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "coach_settings",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("settings", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "coach_hint",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("identity", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hint", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "coach_policy",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("policy", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    for table in TABLES:
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
