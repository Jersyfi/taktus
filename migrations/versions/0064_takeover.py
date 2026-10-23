"""A person takes over a running step under the run's lease (ADR-0128, issue #404).

Revision: 0064
Revises: 0063

What this adds to `job`:

- `takeover_by` and `takeover_step`: a take-over asked and not yet served — the claimant the
  claim passes to, which names the take-over and never a person, and the step it is asked for.
  One statement sets them only where they are empty, so that only the first asker succeeds.
- `held_until`: for a claim passed to a take-over, until when it is held. `claim_jobs` holds
  such a job to that time instead of the lease — skipped before it, claimable from it — and
  clears it on the claim that follows.

Jobs that exist were never taken over: null, which is what happened. The function's name,
arguments, grant and result columns it already returned are unchanged; it returns the job's
row, which has three columns more, and is replaced rather than altered.

The previous release neither reads nor writes the three columns (ADR-0093). Its runners call
`claim_jobs`, which now skips a held job for them too; no job is held until this release has
passed a claim.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

ROLE = "taktus_app"

HELD_SKIPPED = """
CREATE OR REPLACE FUNCTION claim_jobs(
    claimant text, batch integer, lease interval, max_attempts integer
)
RETURNS SETOF job
LANGUAGE sql AS $$
    WITH picked AS MATERIALIZED (
        SELECT tenant, id FROM job
        WHERE available_at <= now()
          AND attempts - deferrals < max_attempts
          AND CASE
                WHEN held_until IS NOT NULL THEN held_until <= now()
                ELSE claimed_at IS NULL OR claimed_at < now() - lease
              END
        ORDER BY created_at, id
        LIMIT batch
        FOR UPDATE SKIP LOCKED
    )
    UPDATE job
    SET claimed_at = now(), claimed_by = claimant, attempts = job.attempts + 1,
        held_until = NULL
    FROM picked
    WHERE job.tenant = picked.tenant AND job.id = picked.id
    RETURNING job.*
$$
"""

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

GRANT = f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer) TO {ROLE}"


def upgrade() -> None:
    op.add_column("job", sa.Column("takeover_by", sa.Text))
    op.add_column("job", sa.Column("takeover_step", sa.Text))
    op.add_column("job", sa.Column("held_until", sa.DateTime(timezone=True)))
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    op.execute(HELD_SKIPPED)
    op.execute(GRANT)


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    op.drop_column("job", "held_until")
    op.drop_column("job", "takeover_step")
    op.drop_column("job", "takeover_by")
    op.execute(DEFERRALS_NOT_COUNTED)
    op.execute(GRANT)
