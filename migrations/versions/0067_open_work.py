"""A cap on a process's open work (ADR-0132, UC-8.12).

Revision: 0067
Revises: 0066

What this adds: `process_version.open_work`, nullable: the cap on each kind of the version's open
outcomes, as the bundle declares it under `open_work`. Every version stored before has none,
which is what it declared: no version could declare a cap before this release.

The previous release neither reads nor writes the column (ADR-0093). It reads a version by the
columns it names, so a version this release stores with a cap is read there without it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("process_version", sa.Column("open_work", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("process_version", "open_work")
