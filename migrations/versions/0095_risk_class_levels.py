"""A risk class carries a level: a ceiling for every step that uses one of its actions
(ADR-0170, UC-7.1).

Revision: 0095
Revises: 0090

What this adds: `anchor_configuration.levels`, nullable: the ceiling of each risk class a
tenant set, as a document from the class's name to its level. Every configuration stored
before set none, which is what it did: no ceiling holds until a person configures one.

The migration only expands. The previous release neither reads nor writes the column: it reads
and writes a configuration by the columns it names (ADR-0093).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0095"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("anchor_configuration", sa.Column("levels", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column("anchor_configuration", "levels")
