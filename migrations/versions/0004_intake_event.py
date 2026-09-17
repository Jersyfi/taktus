"""Intake events: the channel's half of a command, kept until the identity component completes
it (control-plane.md §2).

Revision: 0004
Revises: 0003

What this creates: `intake_event`, one row per delivery a connector accepted through the
webhook intake of the HTTP surface. The primary key is the source system's identifier for the
delivery, so that a redelivery replaces the row rather than adding one. The row carries what
the connector normalised — the event kind, the sender as the source system names them (an
opaque account, never a name), the intent, the channel context, the reply address — and a
status, `awaiting_identity`, until the identity component maps the sender. Tenant and
row-level security as on every table (ADR-0020); the application role may read, insert,
update and delete it as it may a command.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "intake_event"


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("event", sa.Text, nullable=False),
        sa.Column("sender_account", sa.Text, nullable=False),
        sa.Column("sender_kind", sa.Text, nullable=False),
        sa.Column("intent", sa.Text, nullable=False),
        sa.Column("context", JSONB, nullable=False),
        sa.Column("reply_channel", sa.Text, nullable=False),
        sa.Column("reply_address", sa.Text, nullable=False),
        sa.Column("reply_thread", sa.Text),
        _at("occurred_at"),
        _at("received_at"),
        sa.Column("status", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("intake_event_received", TABLE, ["tenant", "received_at"])
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
    op.drop_index("intake_event_received", table_name=TABLE)
    op.drop_table(TABLE)
