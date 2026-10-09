"""The conformance half of an adapter's maturity, recorded as a document.

Revision: 0019
Revises: 0018

What this changes: `adapter_maturity` gains `conformance`, the last run of the contract's
conformance suite that the instance ran itself against the adapter (ADR-0044) — the contract
and its version, the Taktus version, the configuration it was taken under, the outcome with the
checks that did not pass, the digest of the evidence, the time and the actor. It is written by
the catalog component in the transaction that writes the ledger entry `conformance.tested`.
`conformance_passed_at`, which nothing wrote before, is now written from it for a reader of
the table: the time of the last run, when that run passed. Nothing is dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

TABLE = "adapter_maturity"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("conformance", JSONB, nullable=True))


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_column(TABLE, "conformance")
