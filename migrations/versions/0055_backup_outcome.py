"""Every run of the backup records its outcome (ADR-0106, amending ADR-0087).

Revision: 0055
Revises: 0054

What this adds: `backup_outcome`, one row per tenant for every run of the backup program: when
it ran, the backup's name, `ok` or `failed`, and for a failure the step that failed as a token.
The program inserts the rows with the login it backs up with, which reads every row and is
outside row-level security (ADR-0087 §2). The application role may only read them. Tenant and
row-level security as on every other table (ADR-0020): each tenant reads its own rows. A row is
never changed. The previous release reads nothing of it, and the previous backup image writes
nothing to it (ADR-0093).
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "backup_outcome"


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        _at("at"),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.PrimaryKeyConstraint("tenant", "name"),
        sa.CheckConstraint("outcome IN ('ok', 'failed')", name="backup_outcome_outcome"),
        sa.CheckConstraint("(outcome = 'ok') = (reason IS NULL)", name="backup_outcome_reason"),
    )
    op.create_index("backup_outcome_newest", TABLE, ["tenant", "at"])
    # The role and the table name are constants of this file, not input.
    op.execute(f"GRANT SELECT ON {TABLE} TO {ROLE}")
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
