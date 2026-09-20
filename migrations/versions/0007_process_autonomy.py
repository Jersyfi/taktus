"""A process version carries its autonomy with its reason (ADR-0026).

Revision: 0007
Revises: 0006

What this adds: `process_version.autonomy`, the level, the reason the process runs at that
level, and what is missing to go one level higher — the statement every process shows
wherever it is shown. `autonomy_level` stays as the level alone, for a query. Rows that exist
were registered before the reason was required; they receive a statement that says so, and
the next registration of the version replaces it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLE = "process_version"
BACKFILL = (
    "jsonb_build_object("
    "'level', autonomy_level, "
    "'reason', 'registered before ADR-0026 required a reason; the next registration states it'"
    ") || CASE WHEN autonomy_level < 4 THEN "
    "jsonb_build_object('toward_next', 'not stated: registered before ADR-0026') "
    "ELSE '{}'::jsonb END"
)


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("autonomy", JSONB))
    # The expression is a constant of this file, not input.
    op.execute(f"UPDATE {TABLE} SET autonomy = {BACKFILL}")  # noqa: S608 — constants of this file
    op.alter_column(TABLE, "autonomy", nullable=False)


def downgrade() -> None:
    op.drop_column(TABLE, "autonomy")
