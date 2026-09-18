"""A run acts on behalf of an identity and carries its inputs; a step run counts its attempts;
an intake event records the command it was completed into.

Revision: 0005
Revises: 0004

What this adds, for the action direction of the connector port (`contracts/connector/v1` §5)
and the provisional identity (DEC-0013):

- **`run.identity`** — on whose behalf the run acts: the identity of the command that
  commissioned the plan. Every connector call carries it, and the target system's permissions
  for it stand. Rows that exist were created by `taktusctl run`, which attributed them to its
  `--identity` label; they receive that label's default.
- **`run.inputs`** — what the run was given when it started (an issue number, a repository),
  which `$input` references in a step's work resolve to. Existing rows had none.
- **`process_version.inputs`** — what a bundle declares it needs: name, description, example.
  Existing rows declared none.
- **`step_run.attempt`** — how many times the step was started afresh: a resume from a stop
  continues the attempt, a retry after a failure the connector called not retryable starts a
  new one. The idempotency key of a connector call is derived from run, step and attempt, never
  stored. Existing rows are on their first attempt.
- **`step_run.retryable`** — after a failure, whether the same call with the same key may be
  repeated without a second effect, as the connector said; null otherwise.
- **`intake_event.command_id`, `intake_event.completed_at`** — set when the event was
  completed into a command by the identity the identity port answered; the status becomes
  `completed`. A redelivery of a completed event completes nothing twice.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run", sa.Column("identity", sa.Text, nullable=False, server_default="idn_local"))
    op.add_column("run", sa.Column("inputs", JSONB, nullable=False, server_default="{}"))
    op.add_column(
        "process_version", sa.Column("inputs", JSONB, nullable=False, server_default="{}")
    )
    op.add_column("step_run", sa.Column("attempt", sa.Integer, nullable=False, server_default="1"))
    op.add_column("step_run", sa.Column("retryable", sa.Boolean))
    op.add_column("intake_event", sa.Column("command_id", sa.Text))
    op.add_column("intake_event", sa.Column("completed_at", sa.DateTime(timezone=True)))
    # The defaults exist for the rows that were there; new rows always carry a value.
    op.alter_column("run", "identity", server_default=None)
    op.alter_column("run", "inputs", server_default=None)
    op.alter_column("process_version", "inputs", server_default=None)
    op.alter_column("step_run", "attempt", server_default=None)


def downgrade() -> None:
    op.drop_column("intake_event", "completed_at")
    op.drop_column("intake_event", "command_id")
    op.drop_column("step_run", "retryable")
    op.drop_column("step_run", "attempt")
    op.drop_column("process_version", "inputs")
    op.drop_column("run", "inputs")
    op.drop_column("run", "identity")
