"""What a process version declares beyond its graph, stored (ADR-0252, ADR-0254, ADR-0255,
ADR-0272, ADR-0273, DEC-0233).

Revision: 0104
Revises: 0102

What this adds, on `process_version`:

- `escalation`, whom a failure's escalation reaches, by which path, and the time to react
  (ADR-0252), and `heal_limit`, how often the same failure is healed before it is said
  (ADR-0254). Both were declared by a version and not stored, so a version read back from the
  database lost them (DEC-0233);
- `frame`, what Taktus may change in the process on its own, and `change_record`, what led
  Taktus to a version it registered within the frame (ADR-0255);
- `control`, where the process's control sits, and for a decoupled one where its task's state
  is read (ADR-0272);
- `contracts`, the data contract of every exchange with a partner (ADR-0273).

Null on every version stored before: no escalation declared, the default limit of three, no
frame and no change. The previous release neither reads nor writes them; a null column changes
no answer it gives (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0104"
down_revision = "0102"
branch_labels = None
depends_on = None

COLUMNS = ("escalation", "heal_limit", "frame", "change_record", "control", "contracts")


def upgrade() -> None:
    op.add_column("process_version", sa.Column("escalation", JSONB, nullable=True))
    op.add_column("process_version", sa.Column("heal_limit", sa.Integer, nullable=True))
    op.add_column("process_version", sa.Column("frame", JSONB, nullable=True))
    op.add_column("process_version", sa.Column("change_record", JSONB, nullable=True))
    op.add_column("process_version", sa.Column("control", JSONB, nullable=True))
    op.add_column("process_version", sa.Column("contracts", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    for column in reversed(COLUMNS):
        op.drop_column("process_version", column)
