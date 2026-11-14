"""A version's runs are read newest first, by state, without reading the tenant's other runs
(ADR-0319).

Revision: 0112
Revises: 0111

What this adds: one index, no table and no column. `run_version_created` orders a tenant's runs
of one process version by creation time and id: how the process level reads the runs of its
version not yet ended and a page of those that ended, how `GET /runs?process=` pages, and how a
version's runs are counted by state. The previous release neither reads nor writes anything
differently because of it (ADR-0093).
"""

from __future__ import annotations

from alembic import op

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("run_version_created", "run", ["tenant", "process_version", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("run_version_created", table_name="run")
