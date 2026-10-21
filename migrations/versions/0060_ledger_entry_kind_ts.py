"""The Takt rate reads the entries of a kind by time (ADR-0105, #522).

Revision: 0060
Revises: 0059

What this adds: the index `ledger_entry_kind_ts` on `ledger_entry`, which reads a tenant's
entries of one kind recorded at or after a moment without reading the others. No table, column
or row changes. The previous release neither reads nor needs it.
"""

from __future__ import annotations

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ledger_entry_kind_ts", "ledger_entry", ["tenant", "kind", "ts"])


def downgrade() -> None:
    # It drops an index only, which is rebuilt from the table. Never run without asking
    # (CLAUDE.md §9).
    op.drop_index("ledger_entry_kind_ts", table_name="ledger_entry")
