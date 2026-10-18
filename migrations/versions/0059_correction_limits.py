"""Corrections are counted, and a level falls by rule (ADR-0110, UC-7.5).

Revision: 0059
Revises: 0058

What this adds: `correction_limits`, one row per tenant that set when Taktus proposes a raise
and when a correction rate lowers a level. A tenant without a row holds the shipped default
(NTC-0215). The table starts empty. Tenant and row-level security as on every other table
(ADR-0020); the application role may read and write it.

Nothing else changes shape. The decisions and the lowered levels are ledger entries, whose
`refs` is a document already; an incident about a level is a row of `incident` (migration 0056).
The previous release neither reads nor writes the table (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "correction_limits"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limits", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    # The role and the table name are constants of this file, not input.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {ROLE}")
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
