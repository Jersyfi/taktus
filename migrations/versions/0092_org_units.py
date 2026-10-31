"""Departments share the runners fairly, and may hold quotas (ADR-0166, UC-7.11, issue #343).

Revision: 0092
Revises: 0090

What this adds:

- `job.org_unit` and `run.org_unit`: the organisational unit a run runs for, the department or
  group below the tenant. Jobs and runs that exist ran for no unit: null, which is what
  happened.
- `job.quota_held_since`: when a claim first skipped the job because its unit held its
  concurrent runs. The claim that takes the job clears it, and the engine books the stretch.
- `run.org_unit_month`: the month, `YYYY-MM`, in which the run committed its budget to its
  unit's budget quota; null for a run that committed nothing.
- `org_unit_quota`: one row per unit a tenant set a quota for; the quota stays a document.
- `org_unit_spend`: what a unit's runs committed in a month, per currency.
- `claim_jobs` with a fifth argument, the units' concurrent limits as a JSON object: it orders
  the due jobs by their unit's places, then by age, and skips a job whose unit holds its limit.

The four-argument `claim_jobs` stays as it was, and the previous release calls it (ADR-0093):
it neither reads nor writes the new columns. It is recreated only because the row type it
returns grew.

Tenant and row-level security on both tables as on every other (ADR-0020).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0092"
down_revision = "0090"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"
TABLES = ("org_unit_quota", "org_unit_spend")


def _due(row: str = "") -> str:
    """The condition that a job is due and claimable, on the row named `row`."""
    r = f"{row}." if row else ""
    return f"""
          {r}available_at <= now()
          AND {r}attempts - {r}deferrals < max_attempts
          AND CASE
                WHEN {r}held_until IS NOT NULL THEN {r}held_until <= now()
                ELSE {r}claimed_at IS NULL OR {r}claimed_at < now() - lease
              END
"""


FOUR = f"""
CREATE FUNCTION claim_jobs(
    claimant text, batch integer, lease interval, max_attempts integer
)
RETURNS SETOF job
LANGUAGE sql AS $$
    WITH picked AS MATERIALIZED (
        SELECT tenant, id FROM job
        WHERE {_due()}
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
"""  # noqa: S608 — constants of this file

# A job's place: the claims its unit holds, plus its position among its unit's due jobs. The
# order by place shares the places between units; a unit's limit skips a place beyond it.
FIVE = f"""
CREATE FUNCTION claim_jobs(
    claimant text, batch integer, lease interval, max_attempts integer, per_unit jsonb
)
RETURNS SETOF job
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH held AS (
        SELECT org_unit, count(*) AS n FROM job
        WHERE claimed_by IS NOT NULL AND held_until IS NULL AND claimed_at >= now() - lease
        GROUP BY org_unit
    ),
    due AS (
        SELECT j.tenant, j.id, j.created_at, j.org_unit,
               coalesce(h.n, 0)
                 + row_number() OVER (PARTITION BY j.org_unit ORDER BY j.created_at, j.id)
                 AS place
        FROM job j LEFT JOIN held h ON h.org_unit IS NOT DISTINCT FROM j.org_unit
        WHERE {_due("j")}
    ),
    ranked AS (
        SELECT due.tenant, due.id, due.place, due.created_at FROM due
        WHERE due.org_unit IS NULL
           OR NOT (per_unit ? due.org_unit)
           OR due.place <= (per_unit ->> due.org_unit)::integer
    ),
    picked AS MATERIALIZED (
        SELECT job.tenant, job.id FROM job
        JOIN ranked ON job.tenant = ranked.tenant AND job.id = ranked.id
        -- Checked again on the locked row: a claim that committed meanwhile took it.
        WHERE {_due("job")}
        ORDER BY ranked.place, ranked.created_at, ranked.id
        LIMIT batch
        FOR UPDATE OF job SKIP LOCKED
    )
    UPDATE job
    SET claimed_at = now(), claimed_by = claimant, attempts = job.attempts + 1,
        held_until = NULL
    FROM picked
    WHERE job.tenant = picked.tenant AND job.id = picked.id
    RETURNING job.*;

    -- What was returned carries when the job was first held; the job itself no longer is.
    UPDATE job SET quota_held_since = NULL
    WHERE claimed_by = claimant AND claimed_at = now() AND quota_held_since IS NOT NULL;

    -- The due jobs of every unit that now holds its limit wait for it, from now on.
    UPDATE job SET quota_held_since = now()
    WHERE (job.tenant, job.id) IN (
        SELECT w.tenant, w.id FROM job w
        WHERE w.quota_held_since IS NULL
          AND w.org_unit IS NOT NULL
          AND per_unit ? w.org_unit
          AND {_due("w")}
          AND (
              SELECT count(*) FROM job c
              WHERE c.org_unit = w.org_unit AND c.claimed_by IS NOT NULL
                AND c.held_until IS NULL AND c.claimed_at >= now() - lease
          ) >= (per_unit ->> w.org_unit)::integer
        FOR UPDATE OF w SKIP LOCKED
    );
END
$$
"""  # noqa: S608 — constants of this file

GRANT_FOUR = f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer) TO {ROLE}"
GRANT_FIVE = (
    f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer, interval, integer, jsonb) TO {ROLE}"
)


def upgrade() -> None:
    op.add_column("job", sa.Column("org_unit", sa.Text))
    op.add_column("job", sa.Column("quota_held_since", sa.DateTime(timezone=True)))
    op.add_column("run", sa.Column("org_unit", sa.Text))
    op.add_column("run", sa.Column("org_unit_month", sa.Text))
    op.create_table(
        "org_unit_quota",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quota", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "org_unit_spend",
        sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("org_unit", sa.Text, nullable=False),
        sa.Column("month", sa.Text, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("committed", sa.Numeric, nullable=False),
        sa.PrimaryKeyConstraint("tenant", "org_unit", "month", "currency"),
    )
    for table in TABLES:
        # The role and the table names are constants of this file, not input.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
        )
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    op.execute(FOUR)
    op.execute(GRANT_FOUR)
    op.execute(FIVE)
    op.execute(GRANT_FIVE)


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer, jsonb)")
    op.execute("DROP FUNCTION claim_jobs(text, integer, interval, integer)")
    for table in TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
        op.drop_table(table)
    op.drop_column("run", "org_unit_month")
    op.drop_column("run", "org_unit")
    op.drop_column("job", "quota_held_since")
    op.drop_column("job", "org_unit")
    op.execute(FOUR)
    op.execute(GRANT_FOUR)
