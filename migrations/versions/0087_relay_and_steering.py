"""The outbound binding's relay, and a person's message to a running step (ADR-0156, #625, #624).

Revision: 0087
Revises: 0086

What this adds:

- `worker_relay`: one row per request a runner relays to a worker connected outbound — the
  worker's adapter identifier, the request as `RelayRequest`, when a host took it, the answer's
  status and type, whether its body ended, and how many answers were posted. A request the
  runner read to its end, or stopped reading, is deleted with its chunks. `worker_relay_chunk`:
  the answer's body in the order it arrived. Both belong to the instance, not to a tenant: row
  security admits only a transaction that sets `taktus.relay` to `on`, which no tenant's
  transaction does.
- `job.messages`, nullable: the persons' messages asked on a run's job, each with its text,
  which the job carries to its runner and drops with itself (ADR-0156 §7). Every job stored
  before carries none, which is what happened.
- `step_run.messages`, nullable: the messages a step's worker received. Every step run stored
  before received none.

The migration only expands. The previous release neither reads nor writes the new tables or
columns (ADR-0093), so `taktus_oldest_code()` stays.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
RELAY = "current_setting('taktus.relay', true) = 'on'"


def upgrade() -> None:
    op.add_column("job", sa.Column("messages", JSONB, nullable=True))
    op.add_column("step_run", sa.Column("messages", JSONB, nullable=True))
    op.create_table(
        "worker_relay",
        sa.Column("request_id", sa.Text, primary_key=True),
        sa.Column("worker", sa.Text, nullable=False),
        sa.Column("envelope", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Integer),
        sa.Column("content_type", sa.Text),
        sa.Column("ended", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("answers", sa.Integer, nullable=False, server_default=sa.text("0")),
    )
    op.create_index(
        "worker_relay_waiting",
        "worker_relay",
        ["worker", "created_at"],
        postgresql_where=sa.text("taken_at IS NULL"),
    )
    op.create_table(
        "worker_relay_chunk",
        sa.Column(
            "request_id",
            sa.Text,
            sa.ForeignKey("worker_relay.request_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("body", sa.LargeBinary, nullable=False),
        sa.PrimaryKeyConstraint("request_id", "seq"),
    )
    for table in ("worker_relay", "worker_relay_chunk"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY relay_host ON {table} TO {ROLE} USING ({RELAY}) WITH CHECK ({RELAY})"
        )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.drop_table("worker_relay_chunk")
    op.drop_table("worker_relay")
    op.drop_column("step_run", "messages")
    op.drop_column("job", "messages")
