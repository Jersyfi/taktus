"""Runs are read newest first a page at a time, and the steps running now are found by state
(ADR-0094).

Revision: 0052
Revises: 0051

What this adds: two indexes, no table and no column. `run_created` orders a tenant's runs by
creation time and id, the order `GET /runs` pages through. `step_run_state` finds a tenant's
step runs by state, which is how the overview finds the steps running now. The previous release
neither reads nor writes anything differently because of them (ADR-0093).
"""

from __future__ import annotations

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("run_created", "run", ["tenant", "created_at", "id"])
    op.create_index("step_run_state", "step_run", ["tenant", "state"])


def downgrade() -> None:
    op.drop_index("step_run_state", table_name="step_run")
    op.drop_index("run_created", table_name="run")
