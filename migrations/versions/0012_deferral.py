"""A step waits for a free place at its worker (ADR-0037).

Revision: 0012
Revises: 0011

What this adds:

- `job.deferrals`: how many claims of a job ended *deferred* — given back to be claimed again
  after a delay because the run's worker was at capacity. A deferral is not a failed attempt:
  `claim_jobs` now holds a job to the limit of attempts by its claims less its deferrals. A
  run that waits an hour for its worker is not left for a person after five tries. A deferred
  job sets `available_at` to when it may be claimed again, which `claim_jobs` already honours.
- `step_run.waiting_since` and `step_run.waits`: when the step's current wait began and how
  many times its worker answered at capacity in it. The step's ceiling is measured from the
  first, the next delay grows with the second.

Jobs and step runs that exist were never deferred and never waited: 0 and null, which is what
happened. The function's name, arguments, grant and result are unchanged.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ROLE = "taktus_app"

DEFERRALS_NOT_COUNTED = """
CREATE OR REPLACE FUNCTION claim_jobs(
    claimant text, batch integer, lease interval, max_attempts integer
)
RETURNS SETOF job
LANGUAGE sql AS $$
    WITH picked AS MATERIALIZED (
        SELECT tenant, id FROM job
        WHERE available_at <= now()
          AND attempts - deferrals < max_attempts
          AND (claimed_at IS NULL OR claimed_at < now() - lease)
        ORDER BY created_at, id
        LIMIT batch
        FOR UPDATE SKIP LOCKED
    )
    UPDATE job
    SET claimed_at = now(), claimed_by = claimant, attempts = job.attempts + 1
    FROM picked
    WHERE job.tenant = picked.tenant AND job.id = picked.id
    RETURNING job.*
$$
"""

EVERY_CLAIM_COUNTED = """
CREATE OR REPLACE FUNCTION claim_jobs(
    claimant text, batch integer, lease interval, max_attempts integer
)
RETURNS SETOF job
LANGUAGE sql AS $$
    WITH picked AS MATERIALIZED (
        SELECT tenant, id FROM job
        WHERE available_at <= now()
          AND attempts < max_attempts
          AND (claimed_at IS NULL OR claimed_at < now() - lease)
        ORDER BY created_at, id
        LIMIT batch
        FOR UPDATE SKIP LOCKED
    )
    UPDATE job
    SET claimed_at = now(), claimed_by = claimant, attempts = job.attempts + 1
    FROM picked
    WHERE job.tenant = picked.tenant AND job.id = picked.id
    RETURNING job.*
$$
"""

GRANT = f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer) TO {ROLE}"


def upgrade() -> None:
    op.add_column(
        "job", sa.Column("deferrals", sa.Integer, nullable=False, server_default=sa.text("0"))
    )
    op.add_column("step_run", sa.Column("waiting_since", sa.DateTime(timezone=True)))
    op.add_column(
        "step_run", sa.Column("waits", sa.Integer, nullable=False, server_default=sa.text("0"))
    )
    # The function returns the job's row, which has a column more now: replaced, not altered.
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    op.execute(DEFERRALS_NOT_COUNTED)
    op.execute(GRANT)


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    op.drop_column("step_run", "waits")
    op.drop_column("step_run", "waiting_since")
    op.drop_column("job", "deferrals")
    op.execute(EVERY_CLAIM_COUNTED)
    op.execute(GRANT)
