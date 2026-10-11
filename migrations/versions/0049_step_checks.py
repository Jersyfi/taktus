"""The checks a step declares from the catalogue (UC-4.13, ADR-0082).

Revision: 0049
Revises: 0027

What this changes: `step` gains `checks`, the list of checks the step declares from the
catalogue of `contracts/shared/v1/Check.json`, as JSON. A step stored before this column existed
has none, and reads as it did: the refusal of an `exact` step without a check is held where a
bundle registers, never on a stored version. Nothing is dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0049"
down_revision = "0027"
branch_labels = None
depends_on = None

TABLE = "step"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("checks", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column(TABLE, "checks")
