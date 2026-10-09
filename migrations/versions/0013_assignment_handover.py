"""A step's assignment is recorded before it is handed over (ADR-0038).

Revision: 0013
Revises: 0012

What this adds:

- `step_run.assignment_open`: whether the assignment `assignment_id` names was handed to the
  worker and the run has not read its end. It is committed before the assignment is posted. A
  runner that recovers a run asks the worker about an open assignment before it hands over
  another, and adopts it or posts it again under the same id.
- `step_run.assignment_seq`: the sequence number of the last event of that assignment whose
  effect the step run holds — the worker's last boundary persisted. Whoever adopts the
  assignment reads its event stream after it.

Step runs that exist are given false and 0. Their assignments were never recorded as open, so
nothing is asked about them; that is how they were handled until now.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "step_run",
        sa.Column("assignment_open", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "step_run",
        sa.Column("assignment_seq", sa.Integer, nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("step_run", "assignment_seq")
    op.drop_column("step_run", "assignment_open")
