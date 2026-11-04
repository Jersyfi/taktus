"""Takeover instructions on every process version, and the trials of them (ADR-0180, UC-6.3).

Revision: 0098
Revises: 0097

What this adds: the column `process_version.takeover`, how a person runs the version without
Taktus, null on every version stored before; and `takeover_trial`, one row per trial a person
recorded, naming the version, the role that ran it and what was missing. It starts empty.
Tenant and row-level security as on every other table (ADR-0020); the application role may read,
insert and update it, never delete: a trial is a record of what a person did, and the product
writes each one once.

The previous release neither reads the column nor the table; a null column changes no answer
it gives (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "takeover_trial"


def upgrade() -> None:
    op.add_column("process_version", sa.Column("takeover", JSONB, nullable=True))
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("process_id", sa.Text, nullable=False),
        sa.Column("process_version", sa.Text, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
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
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.execute(f"DROP POLICY tenant_isolation ON {TABLE}")
    op.execute(f"REVOKE ALL ON {TABLE} FROM {ROLE}")
    op.drop_table(TABLE)
    op.drop_column("process_version", "takeover")
