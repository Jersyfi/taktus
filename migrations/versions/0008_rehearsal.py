"""A run can be a rehearsal, and every ledger entry of one says so (ADR-0030).

Revision: 0008
Revises: 0007

What this adds:

- **`run.rehearsal`** — whether the run is a rehearsal: a run in which no outward connector
  operation acts, and each answers with the recorded response of an earlier real call.
  The removal test runs its processes this way. Rows that exist were real runs; they receive
  `false`.
- **`ledger_entry.rehearsal`** — true on every entry of a rehearsal run, null on every other.
  Existing entries stay null. Nothing is updated in them: the column is added without a
  default, so the append-only rule of the ledger holds and no hash changes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run", sa.Column("rehearsal", sa.Boolean, nullable=False, server_default=sa.false())
    )
    # The default exists for the rows that were there; new rows always carry a value.
    op.alter_column("run", "rehearsal", server_default=None)
    op.add_column("ledger_entry", sa.Column("rehearsal", sa.Boolean))


def downgrade() -> None:
    op.drop_column("ledger_entry", "rehearsal")
    op.drop_column("run", "rehearsal")
