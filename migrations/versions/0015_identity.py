"""The identity component: identities, the links of channel accounts, link codes.

Revision: 0015
Revises: 0013

What this creates (ADR-0040): `identity`, one row per identity of a tenant with its
organisational path and the digest of its account key; `channel_link`, one row per account on a
channel, keyed by an identifier derived from the two so that an account has at most one link,
with a revoked link kept revoked; `link_code`, the single-use codes a person links an account
with, keyed by the code's digest — the code itself is kept nowhere. And `process.activated_by`,
the identity that registered the active version, whom its schedule triggers act for. Tenant
and row-level security on every new table as on every other (ADR-0020); the application role
may read and write them.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0013"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("identity", "channel_link", "link_code")


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _tenant() -> sa.Column[str]:
    return sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False)


def upgrade() -> None:
    op.add_column("process", sa.Column("activated_by", sa.Text, nullable=True))
    op.create_table(
        "identity",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("org_path", JSONB, nullable=False),
        sa.Column("key_digest", sa.Text, nullable=True),
        _at("created_at"),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "channel_link",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("account", sa.Text, nullable=False),
        sa.Column("identity", sa.Text, nullable=False),
        sa.Column("origin", sa.Text, nullable=False),
        _at("linked_at"),
        _at("revoked_at", nullable=True),
        sa.Column("revoked_by", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "link_code",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("identity", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        _at("created_at"),
        _at("expires_at"),
        _at("used_at", nullable=True),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
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
        op.drop_table(table)
    op.drop_column("process", "activated_by")
