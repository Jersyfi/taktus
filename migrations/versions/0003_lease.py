"""The claim is a lease: a job stays claimed only while its runner keeps it alive.

Revision: 0003
Revises: 0002

Revision 0001 created `claim_jobs(claimant, batch)`: a runner claims due jobs with
`SELECT … FOR UPDATE SKIP LOCKED`, and a claimed row is invisible to every other runner's claim.
It never said how a claim ends when the runner dies. Nothing was using it yet; the daemon does
now (`docs/architecture/project-structure.md` §5), and a runner that is killed mid-run must not
leave its run claimed forever.

What this changes:

- **`claim_jobs(claimant, batch, lease)`** claims a job that is unclaimed *or whose claim is
  older than `lease`*: a claim is a lease that the runner renews by touching `claimed_at`
  (`extend`), and a claim nobody renews expires. Row locking still keeps two claimants apart
  at the moment of claiming; the lease keeps a dead runner from holding a job. `attempts` counts
  every claim, and a job claimed `max_attempts` times is never claimed again — work that fails
  every time stays for a person instead of running forever.
- The old two-argument function is dropped; nothing called it.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ROLE = "taktus_app"

CLAIM = """
CREATE FUNCTION claim_jobs(claimant text, batch integer, lease interval, max_attempts integer)
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

OLD_CLAIM = """
CREATE FUNCTION claim_jobs(claimant text, batch integer) RETURNS SETOF job
LANGUAGE sql AS $$
    UPDATE job
    SET claimed_at = now(), claimed_by = claimant, attempts = attempts + 1
    WHERE (tenant, id) IN (
        SELECT tenant, id FROM job
        WHERE claimed_at IS NULL AND available_at <= now()
        ORDER BY available_at
        LIMIT batch
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *
$$
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION claim_jobs(text, integer)")
    op.execute(CLAIM)
    op.execute(f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer) TO {ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    op.execute(OLD_CLAIM)
    op.execute(f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer) TO {ROLE}")
