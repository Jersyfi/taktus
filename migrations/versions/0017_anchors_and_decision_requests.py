"""Anchors at the step boundary, decision requests and the decision register (ADR-0042).

Revision: 0017
Revises: 0016

What this adds:

- `anchor_configuration`: one row per tenant that configured its anchors — the anchors in the
  shape of `Anchor.json` and the risk classes, as documents. A tenant without a row holds the
  shipped default.
- `decision_request`: one row per decision request — the request in the shape of
  `DecisionRequest.json`, and beside it the role that decides, the status and the times the
  decider's list and the response times are read from.
- `register_entry`: one row per entry of the decision register, linked to the run, the step
  and the request.
- `step_run.anchoring`: the requests an anchored step raised and what was decided.
- `identity.roles`: the roles an identity holds; an anchor names the role that decides.

Existing runs raised no request and existing identities hold no role: null and an empty list,
which is what held for them. Tenant and row-level security on every new table as on every other
(ADR-0020); the application role may read and write them.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("anchor_configuration", "decision_request", "register_entry")


def _at(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _tenant() -> sa.Column[str]:
    return sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False)


def upgrade() -> None:
    op.add_column(
        "identity",
        sa.Column("roles", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("step_run", sa.Column("anchoring", JSONB))
    op.create_table(
        "anchor_configuration",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("anchors", JSONB, nullable=False),
        sa.Column("risk_classes", JSONB, nullable=False),
        _at("configured_at", nullable=True),
        sa.Column("configured_by", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "decision_request",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("decider", sa.Text, nullable=False),
        sa.Column("anchor", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        _at("raised_at"),
        sa.Column("request", JSONB, nullable=False),
        sa.Column("answered_by", sa.Text, nullable=True),
        _at("answered_at", nullable=True),
        sa.Column("reflection", sa.Text, nullable=True),
        sa.Column("decided_by", sa.Text, nullable=True),
        _at("decided_at", nullable=True),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("decision_request_status", "decision_request", ["tenant", "status"])
    op.create_table(
        "register_entry",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("request_id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("entry", JSONB, nullable=False),
        _at("decided_at"),
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
    op.drop_table("register_entry")
    op.drop_index("decision_request_status", table_name="decision_request")
    op.drop_table("decision_request")
    op.drop_table("anchor_configuration")
    op.drop_column("step_run", "anchoring")
    op.drop_column("identity", "roles")
