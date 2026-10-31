"""Data-protection requests, prepared and carried out by a person (ADR-0176, UC-11.2).

Revision: 0097
Revises: 0096

What this adds: `subject_request`, one row per data-protection request — access,
rectification, erasure or portability — with its kind, its state and the request as a
document. It starts empty. Tenant and row-level security as on every other table (ADR-0020);
the application role may read, insert and update it. A row is never deleted: its state moves
on, so that a request can be answered for later.

And the index `provenance_scope_subject` over the subject a provenance record's scope names, so
that the steps that served a subject's cases are found without reading the rest. The trigger
that refuses an update or a delete of a record is untouched: an index changes no record
(ADR-0021).

The previous release neither reads nor writes the table, and an index changes no answer
(ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLE = "subject_request"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request", JSONB, nullable=False),
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
    op.create_index(
        "provenance_scope_subject", "provenance", ["tenant", sa.text("(scope ->> 'subject')")]
    )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_index("provenance_scope_subject", table_name="provenance")
    op.execute(f"DROP POLICY tenant_isolation ON {TABLE}")
    op.execute(f"REVOKE ALL ON {TABLE} FROM {ROLE}")
    op.drop_table(TABLE)
