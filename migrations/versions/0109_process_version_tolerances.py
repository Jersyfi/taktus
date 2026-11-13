"""The tolerance a variable step declares before its process has cases, stored (ADR-0300).

Revision: 0109
Revises: 0108

What this adds, on `process_version`: `tolerances`, the share by which each variable step's
result may differ under the same version, declared beside the steps where the process has no
evaluation yet (ADR-0300 §1). A version read back from the database would otherwise lose it, as
DEC-0233 found for `escalation` and `heal_limit`.

Null on every version stored before: no tolerance declared beside the steps. The previous
release neither reads nor writes it; a null column changes no answer it gives (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("process_version", sa.Column("tolerances", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("process_version", "tolerances")
