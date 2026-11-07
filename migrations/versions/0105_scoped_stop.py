"""A stop can be scoped to a process or a tenant, and a rule may request one (ADR-0256, UC-7.2).

Revision: 0105
Revises: 0100

What this adds: `scoped_stop`, one row per stop of a process or of a tenant, requested by a
person or by a rule, never deleted: its state moves from holding to confirmed to lifted. It
starts empty. A stop of an adapter stays in `adapter_stop`.

Tenant and row-level security as on every other table (ADR-0020); the application role may read
and write it. The previous release neither reads nor writes the table (ADR-0093): a stop of a
process requested while it still runs reaches no runner of that release, and the stops of
adapters it reads are the ones it wrote.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0105"
down_revision = "0100"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "scoped_stop"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("process", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stop", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("scoped_stop_state", TABLE, ["tenant", "state"])
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
