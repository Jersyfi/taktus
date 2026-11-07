"""An entry of the catalogue is shared with circles, and a caller's own credential is bound to
an identity (ADR-0246, ADR-0247).

Revision: 0103
Revises: 0105

What this adds:

- `catalogue_share`, one row per model, agent, connector or skill shared with circles of the
  organisation's structure: its kind, its subject, its state and when it was shared, beside the
  share as a document — its owner, purpose, circles and, for a model, where it processes data,
  its cost model and its origin.
- `caller_credential`, one row per identity and credential name: the suffix of the parameter
  the identity's own value is provided under. It holds a parameter's name, never a value.

Both start empty, with tenant and row-level security as on every other table (ADR-0020). The
application role may read, insert and update them; nothing deletes a row: a share is withdrawn
and a binding is replaced.

The migration only expands. The previous release neither reads nor writes the tables
(ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0103"
down_revision = "0105"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("catalogue_share", "caller_credential")


def _tenant() -> sa.Column[str]:
    return sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False)


def _secured(table: str) -> None:
    # The role and the table names are constants of this file, not input.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
    )


def upgrade() -> None:
    op.create_table(
        "catalogue_share",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("share", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "caller_credential",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("identity", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("suffix", sa.Text, nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    for table in TABLES:
        _secured(table)


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        op.drop_table(table)
