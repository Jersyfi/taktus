"""A claim takes at most its batch, whatever plan the database chooses.

Revision: 0010
Revises: 0009

Revision 0003 wrote `claim_jobs` as an `UPDATE … WHERE (tenant, id) IN (SELECT … LIMIT batch
FOR UPDATE SKIP LOCKED)`. The `LIMIT` holds for one execution of the inner query, and the
database may execute it more than once. When its statistics say that the job table is empty —
a fresh database, or one not analysed since it filled — it plans a nested loop that executes
the inner query again for every row of the table. Each execution skips the rows the statement
has already updated and takes the next ones. One claim with a batch of two then took every due
job of the tenant (issue #73, NTC-0027). A runner started all of them at once, above its
concurrency, and a worker at capacity failed the rest.

What this changes: the inner query becomes a `MATERIALIZED` common table expression, which the
database executes exactly once, and the update joins it. The function's name, arguments, grant
and result are unchanged.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ROLE = "taktus_app"

ONCE = """
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

PER_ROW = """
CREATE OR REPLACE FUNCTION claim_jobs(
    claimant text, batch integer, lease interval, max_attempts integer
)
RETURNS SETOF job
LANGUAGE sql AS $$
    UPDATE job
    SET claimed_at = now(), claimed_by = claimant, attempts = attempts + 1
    WHERE (tenant, id) IN (
        SELECT tenant, id FROM job
        WHERE available_at <= now()
          AND attempts < max_attempts
          AND (claimed_at IS NULL OR claimed_at < now() - lease)
        ORDER BY created_at, id
        LIMIT batch
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *
$$
"""


def upgrade() -> None:
    op.execute(ONCE)
    op.execute(f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer) TO {ROLE}")


def downgrade() -> None:
    op.execute(PER_ROW)
    op.execute(f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer) TO {ROLE}")
