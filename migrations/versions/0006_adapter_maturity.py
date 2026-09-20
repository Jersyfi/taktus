"""The maturity of an adapter: what the removal test found, per adapter identifier.

Revision: 0006
Revises: 0005

What this creates: `adapter_maturity`, one row per adapter identifier — `worker.endpoint`,
`connector.<label>`, `model.endpoint`, never a product name (ADR-0003) — with the family, the
moment the conformance suite was recorded as passed (nothing writes it yet), the last removal
result as its document, and when the row was last written. The removal test
(`blueprints/self-operation/`) writes it through the catalog component; the ledger carries the
matching `removal.tested` entry. Tenant and row-level security as on every table (ADR-0020);
the application role may read and write it as it may a process.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "adapter_maturity"


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("family", sa.Text, nullable=False),
        _at("conformance_passed_at", nullable=True),
        sa.Column("removal", JSONB),
        _at("updated_at"),
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
