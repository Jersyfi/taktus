"""Skills move through their lifecycle, and a shared agent has a core and role profiles
(ADR-0162, ADR-0163, issues #646 and #647).

Revision: 0090
Revises: 0089

What this adds:

- `skill_version`, one row per version of a skill a tenant registered: its name, its stage and
  when it was registered beside the version as a document — the parsed `SKILL.md`, its origin,
  its owner, its rounds and measurements.
- `skill_ownership`, one row per skill version drawn from one person's own use: the person it
  belongs to, kept apart from every score of the skill (principle 14).
- `skill_policy`, one row per tenant that set its own n for automatic approval at level 4. A
  tenant without a row holds the shipped floor (NTC-0246).
- `agent_core` and `role_profile`, one row per version of a shared agent's core and of a role's
  profile, each a document with the columns it is listed by.
- `run.skills`, nullable: the skill versions a run pinned; and `run.profile`, nullable: the role
  profile it serves. Every run stored before pinned none and served none, which is what it did.

Every table starts empty, with tenant and row-level security as on every other (ADR-0020). The
application role may read, insert and update them; nothing deletes a row: a version retires and
a profile is replaced by its next version.

The migration only expands. The previous release neither reads nor writes the tables nor the
columns: it reads and writes a run by the columns it names (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("skill_version", "skill_ownership", "skill_policy", "agent_core", "role_profile")


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
        "skill_version",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("skill", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("skill_version_name", "skill_version", ["tenant", "name"])
    op.create_table(
        "skill_ownership",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("owner", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "skill_policy",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("policy", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "agent_core",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("core", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "role_profile",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    for table in TABLES:
        _secured(table)
    op.add_column("run", sa.Column("skills", JSONB, nullable=True))
    op.add_column("run", sa.Column("profile", sa.Text, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("run", "profile")
    op.drop_column("run", "skills")
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        op.drop_table(table)
