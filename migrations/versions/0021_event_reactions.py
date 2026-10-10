"""When a process's active version was registered, for event reactions.

Revision: 0021
Revises: 0020

What this changes: `process` gains `activated_at`, the moment the active version was
registered. An event received before it does not start the process (ADR-0048 §6). A process
registered before this column existed has none, and its event triggers start nothing until its
version is registered again; its schedule triggers are unaffected. The outbox (migration 0001),
which nothing wrote until now, is written by the intake and read by the automation role; its
shape does not change. Nothing is dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

TABLE = "process"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column(TABLE, "activated_at")
