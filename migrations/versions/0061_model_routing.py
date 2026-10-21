"""A purpose's chain of models, a tenant's residency rule and the route in the provenance
(ADR-0116, UC-8.2).

Revision: 0061
Revises: 0060

What this adds: `residency_rule`, one row per tenant that set where its data may be processed.
A tenant without a row holds `anywhere` (NTC-0217). The table starts empty. Tenant and row-level
security as on every other table (ADR-0020); the application role may read and write it.

And `provenance.route`, nullable: the route a step on a model took through its purpose's chain.
Every record written before has none. The trigger that refuses an update or a delete of a
record is untouched; adding a column changes no record (ADR-0021).

The previous release neither reads nor writes the table nor the column (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "residency_rule"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule", JSONB, nullable=False),
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
    op.add_column("provenance", sa.Column("route", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("provenance", "route")
    op.execute(f"DROP POLICY tenant_isolation ON {TABLE}")
    op.execute(f"REVOKE ALL ON {TABLE} FROM {ROLE}")
    op.drop_table(TABLE)
