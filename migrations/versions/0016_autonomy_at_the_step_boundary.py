"""Autonomy levels are applied at the step boundary (ADR-0039).

Revision: 0016
Revises: 0015

What this adds:

- `run.actions`: the level of each tool action of the process that runs below the process's
  level, as a map from the action — a capability or a connector operation — to its level. A
  step that uses one runs at the lowest level that applies to it.
- `step_run.confirmed_by`: the person who confirmed the step before it started (level 2), or
  who performed its act and reported it (level 1).

Runs that exist carried no action levels and no step was answered by a person: an empty map
and null, which is what held for them. The level of a step is applied before the step starts;
a step of an existing run that has started already is not asked again.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column("actions", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("step_run", sa.Column("confirmed_by", sa.Text))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("step_run", "confirmed_by")
    op.drop_column("run", "actions")
