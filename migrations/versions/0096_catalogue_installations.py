"""What an instance installed from a catalogue, and where it came from (ADR-0175 §4, UC-14.6).

Revision: 0096
Revises: 0095

What this adds: `catalogue_installation`, one row per entry a tenant installed — keyed by the
adapter identifier an image was bound to, or `process.<id>` for a bundle — with the time it was
installed and the record as a document: the index, the entry as verified, its author, who
installed it and the digest of the evidence. The catalog component writes it in the transaction
that writes the ledger entry `catalogue.installed`.

The migration only expands. The previous release neither reads nor writes the table
(ADR-0093). Tenant and row-level security as on every other table (ADR-0020).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "catalogue_installation"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("installation", JSONB, nullable=False),
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
