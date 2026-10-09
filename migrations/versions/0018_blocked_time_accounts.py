"""A step run carries the block it is in (ADR-0043).

Revision: 0018
Revises: 0017

What this adds:

- `step_run.block`: the block the step is in while it waits — its account, its cause token and
  when it began, and for a step held back the step it depends on. The record of the block is
  written when it ends, and the column is cleared.

Step runs that exist were in no block the engine knew of: null. A step that waits at a worker's
capacity since before this migration carries only `waiting_since`; the engine reads that as an
open block booked to `limit.compute` when the wait ends.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("step_run", sa.Column("block", JSONB))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("step_run", "block")
