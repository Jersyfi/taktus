"""A step sees only the data of its case, and an analysis step never speaks outward (ADR-0130,
UC-7.7).

Revision: 0065
Revises: 0064

What this adds: `source_declaration`, one row per tenant that declared which capabilities serve
data free of personal fields and which serve personal data. A tenant without a row declared
neither (NTC-0224). The table starts empty. Tenant and row-level security as on every other
table (ADR-0020); the application role may read and write it.

And `provenance.scope`, nullable: the subject of the case a step served. Every record written
before has none, which is what happened: no step declared a scope before this release. The
trigger that refuses an update or a delete of a record is untouched; adding a column changes no
record (ADR-0021).

The previous release neither reads nor writes the table nor the column (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "source_declaration"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("declaration", JSONB, nullable=False),
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
    op.add_column("provenance", sa.Column("scope", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("provenance", "scope")
    op.execute(f"DROP POLICY tenant_isolation ON {TABLE}")
    op.execute(f"REVOKE ALL ON {TABLE} FROM {ROLE}")
    op.drop_table(TABLE)
