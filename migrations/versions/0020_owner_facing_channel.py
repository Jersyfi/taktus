"""The owner-facing channel and its reports (ADR-0045).

Revision: 0020
Revises: 0019

What this adds:

- `owner_channel`: one row per tenant that configured its owner-facing channel — the owner,
  whom the owner named, where reports go and the phrasebook in the owner's language, as a
  document.
- `report`: one row per report to the owner — a decision request addressed to them, a need, a
  date or a failure Taktus noticed about itself — as a document, and beside it the kind, the
  state and the date it is needed by.

No tenant configured a channel and no report was raised before: both tables start empty.
Tenant and row-level security on every new table as on every other (ADR-0020); the application
role may read and write them.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("owner_channel", "report")


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _tenant() -> sa.Column[str]:
    return sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "owner_channel",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("channel", JSONB, nullable=False),
        _at("configured_at"),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "report",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("due", sa.Date, nullable=False),
        _at("raised_at"),
        sa.Column("report", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("report_state", "report", ["tenant", "state"])
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
    op.drop_index("report_state", table_name="report")
    op.drop_table("report")
    op.drop_table("owner_channel")
