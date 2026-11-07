"""The classes of request a run holds its steps to, and the class its step named (ADR-0215).

Revision: 0099
Revises: 0098

What this adds: the columns `run.classes`, the levels per class of request the run took on
from its version's statement, as far as they were lowered, and `run.case_class`, the class the
run's class step named. Both are null on every run stored before, which named no class.

The previous release neither reads nor writes them; a null column changes no answer it gives
(ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run", sa.Column("classes", JSONB, nullable=True))
    op.add_column("run", sa.Column("case_class", sa.Text, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("run", "case_class")
    op.drop_column("run", "classes")
