"""A budget is a budget: the margin a run is held with, and what each step reserved (ADR-0005).

Revision: 0009
Revises: 0008

What this adds: `run.margin`, the share of every limit the run holds back from the first step
on; and `step_run.reservation`, what admission debited from the budget for the step — its
estimate scaled by the measured error of the adapter that gave it. Runs that exist were
admitted without either: their margin is 0 and they reserved nothing, which is what happened.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run", sa.Column("margin", sa.Float, nullable=False, server_default="0"))
    op.add_column("step_run", sa.Column("reservation", JSONB))


def downgrade() -> None:
    op.drop_column("step_run", "reservation")
    op.drop_column("run", "margin")
