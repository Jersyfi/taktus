"""The input that names a run's case, on every process version (ADR-0216).

Revision: 0100
Revises: 0099

What this adds: the column `process_version.case_input`, the input of the version whose value is
a run's case — the support message, the pull request — by which the spend of the process's runs
is grouped. Null on every version stored before, whose runs are counted per run alone.

The previous release neither reads nor writes it; a null column changes no answer it gives
(ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("process_version", sa.Column("case_input", sa.Text, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("process_version", "case_input")
