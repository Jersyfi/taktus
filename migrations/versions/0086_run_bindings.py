"""A run may bind a purpose to one model for itself alone (ADR-0149 §1, #448).

Revision: 0086
Revises: 0083

What this adds: `run.bindings`, nullable: the purposes a model trial's case run binds to its
candidate, `{purpose: model.<member>}`. Every run stored before binds none, which is what it
did: no run could bind a purpose before this release.

The migration only expands. The previous release neither reads nor writes the column: it
reads and writes a run by the columns it names (ADR-0093), so `taktus_oldest_code()` stays.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0086"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run", sa.Column("bindings", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("run", "bindings")
