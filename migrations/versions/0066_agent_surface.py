"""A person's own agent reaches Taktus over MCP, with a key of its own and the rights of their
role (ADR-0131, UC-1.11).

Revision: 0066
Revises: 0065

What this adds: `identity.agent_key_digest`, nullable: the digest of the agent key a person's
agent proves the identity with on the MCP surface. Every identity written before has none, which
is what happened: no agent key was issued before this release.

And `role_rights`, one row per role of a tenant that was granted a right: the role, and the
rights it holds. The table starts empty; a role without a row holds no right. Tenant and
row-level security as on every other table (ADR-0020). The application role may read, insert and
update it; a right withdrawn is an update, and it deletes nothing.

The previous release neither reads nor writes the table nor the column; its writes of an
identity leave the column as it is (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "role_rights"


def upgrade() -> None:
    op.add_column("identity", sa.Column("agent_key_digest", sa.Text, nullable=True))
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("rights", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    # The role and the table name are constants of this file, not input.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {ROLE}")
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
    op.drop_column("identity", "agent_key_digest")
