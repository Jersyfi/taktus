"""The first schema: tenants, process, run, ledger, queue and outbox (ADR-0002, ADR-0020).

Revision: 0001
Revises: none

What this creates, and why it looks the way it does:

- **Every table carries `tenant`** and its primary key starts with it (ADR-0020). Until the
  identity component exists, one tenant named `default` is created here.
- **Row-level security on every table.** A policy `tenant_isolation` lets a row be seen or
  written only when the session setting `taktus.tenant` names its tenant. The policy is forced,
  so it applies to the table owner as well; only a superuser is outside it. Isolation therefore
  does not depend on every query being written correctly: a query that forgets the filter sees
  nothing, not everything.
- **The application role `taktus_app`.** The adapter assumes it inside every transaction with
  `SET LOCAL ROLE`. It cannot log in and owns nothing; it is granted to the user running this
  migration, so that the same login serves migration and operation. On the ledger it may read
  and insert, nothing else.
- **The ledger is append-only in the database** (ADR-0006), twice: `UPDATE`, `DELETE` and
  `TRUNCATE` are revoked from the application role, and a trigger rejects them for every role
  that is not a superuser. A hash chain whose rows can be edited proves nothing.
- **A foreign key never crosses a component boundary** (ADR-0016): `run` names its plan, `plan`
  its command, `process_version` its process — by id only. Inside an aggregate, children hang
  off their parent with `ON DELETE CASCADE`.
- **Queue and outbox** (`job`, `outbox`) with their claiming primitives — `claim_jobs` and
  `claim_outbox` use `SELECT … FOR UPDATE SKIP LOCKED`, `try_lead` a session advisory lock for
  the scheduler election. **They are not used yet.** ADR-0002 puts them in PostgreSQL and the
  daemon (`docs/architecture/project-structure.md` §5) will claim through them; creating them
  now means the schema is not migrated twice. Nothing in this version reads or writes them.
- The role is not dropped on downgrade: roles are cluster-wide, and another database in the
  same cluster may use it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ROLE = "taktus_app"
SETTING = "taktus.tenant"
CURRENT_TENANT = f"NULLIF(current_setting('{SETTING}', true), '')"

TENANT_SCOPED = (
    "process",
    "process_version",
    "step",
    "command",
    "plan",
    "run",
    "step_run",
    "checkpoint",
    "artifact",
    "ledger_entry",
    "job",
    "outbox",
)


def _tenant() -> sa.Column[str]:
    return sa.Column("tenant", sa.Text, sa.ForeignKey("tenant.id"), nullable=False)


def _at(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        _at("created_at"),
    )
    op.execute("INSERT INTO tenant (id, name, created_at) VALUES ('default', 'default', now())")

    # --- process ----------------------------------------------------------------------------
    op.create_table(
        "process",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("active_version", sa.Text),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "process_version",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("process_id", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("autonomy_level", sa.Integer, nullable=False),
        sa.Column("triggers", JSONB, nullable=False),
        sa.Column("slo", JSONB),
        sa.Column("work", JSONB, nullable=False),
        sa.Column("limits", JSONB),
        sa.Column("author", sa.Text),
        sa.Column("reason", sa.Text),
        sa.PrimaryKeyConstraint("tenant", "id"),
        sa.UniqueConstraint("tenant", "process_id", "version", name="process_version_unique"),
    )
    op.create_table(
        "step",
        _tenant(),
        sa.Column("version_id", sa.Text, nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("rejected", JSONB, nullable=False),
        sa.Column("exactness", sa.Text),
        sa.Column("fallback", JSONB),
        sa.Column("model", sa.Text),
        sa.Column("requires", JSONB),
        sa.Column("depends_on", JSONB),
        sa.PrimaryKeyConstraint("tenant", "version_id", "id"),
        sa.ForeignKeyConstraint(
            ["tenant", "version_id"],
            ["process_version.tenant", "process_version.id"],
            ondelete="CASCADE",
            name="step_version",
        ),
    )

    # --- command ----------------------------------------------------------------------------
    op.create_table(
        "command",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("identity", sa.Text, nullable=False),
        sa.Column("org_path", JSONB, nullable=False),
        sa.Column("intent", JSONB, nullable=False),
        sa.Column("context", JSONB),
        sa.Column("reply_to", JSONB, nullable=False),
        _at("received_at"),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_table(
        "plan",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("command_id", sa.Text, nullable=False),
        sa.Column("goal", sa.Text, nullable=False),
        sa.Column("autonomy_level", sa.Integer, nullable=False),
        _at("due", nullable=True),
        sa.Column("steps", JSONB, nullable=False),
        sa.Column("results_in", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("commissioned_by", sa.Text),
        _at("commissioned_at", nullable=True),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )

    # --- run --------------------------------------------------------------------------------
    op.create_table(
        "run",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("plan_id", sa.Text, nullable=False),
        sa.Column("process_version", sa.Text, nullable=False),
        sa.Column("autonomy_level", sa.Integer, nullable=False),
        sa.Column("budget", JSONB, nullable=False),
        sa.Column("steps", JSONB, nullable=False),
        sa.Column("work", JSONB, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("cause", sa.Text),
        sa.Column("reason", sa.Text),
        _at("created_at"),
        _at("updated_at"),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index("run_state", "run", ["tenant", "state"])
    op.create_table(
        "step_run",
        _tenant(),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("adapter", sa.Text),
        sa.Column("assignment_id", sa.Text),
        sa.Column("estimate", JSONB),
        sa.Column("consumption", JSONB),
        sa.Column("reason", sa.Text),
        _at("started_at", nullable=True),
        _at("finished_at", nullable=True),
        sa.PrimaryKeyConstraint("tenant", "run_id", "step_id"),
        sa.ForeignKeyConstraint(
            ["tenant", "run_id"], ["run.tenant", "run.id"], ondelete="CASCADE", name="step_run_run"
        ),
    )
    op.create_table(
        "checkpoint",
        _tenant(),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("ref", sa.Text, nullable=False),
        _at("taken_at"),
        sa.Column("artifact_ids", JSONB, nullable=False),
        sa.Column("result_digest", sa.Text),
        sa.PrimaryKeyConstraint("tenant", "run_id", "step_id"),
        sa.ForeignKeyConstraint(
            ["tenant", "run_id", "step_id"],
            ["step_run.tenant", "step_run.run_id", "step_run.step_id"],
            ondelete="CASCADE",
            name="checkpoint_step_run",
        ),
    )
    op.create_table(
        "artifact",
        _tenant(),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("digest", sa.Text, nullable=False),
        sa.Column("media_type", sa.Text),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("uri", sa.Text),
        sa.Column("title", sa.Text),
        _at("created_at", nullable=True),
        sa.PrimaryKeyConstraint("tenant", "run_id", "step_id", "id"),
        sa.ForeignKeyConstraint(
            ["tenant", "run_id", "step_id"],
            ["step_run.tenant", "step_run.run_id", "step_run.step_id"],
            ondelete="CASCADE",
            name="artifact_step_run",
        ),
    )

    # --- ledger -----------------------------------------------------------------------------
    op.create_table(
        "ledger_entry",
        _tenant(),
        sa.Column("seq", sa.BigInteger, nullable=False),
        _at("ts"),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("prev_hash", sa.Text),
        sa.Column("hash", sa.Text, nullable=False),
        sa.Column("refs", JSONB, nullable=False),
        sa.Column("method", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("adapter", sa.Text),
        sa.Column("consumption", JSONB),
        sa.Column("outcome", sa.Text),
        sa.Column("content_digest", sa.Text),
        sa.PrimaryKeyConstraint("tenant", "seq"),
    )
    op.create_index("ledger_entry_run", "ledger_entry", ["tenant", sa.text("(refs ->> 'run_id')")])
    op.execute(
        """
        CREATE FUNCTION ledger_entry_is_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entry is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_entry_append_only
        BEFORE UPDATE OR DELETE ON ledger_entry
        FOR EACH ROW EXECUTE FUNCTION ledger_entry_is_append_only()
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_entry_no_truncate
        BEFORE TRUNCATE ON ledger_entry
        FOR EACH STATEMENT EXECUTE FUNCTION ledger_entry_is_append_only()
        """
    )

    # --- queue and outbox: created, not yet used --------------------------------------------
    op.create_table(
        "job",
        _tenant(),
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        _at("available_at"),
        _at("claimed_at", nullable=True),
        sa.Column("claimed_by", sa.Text),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        _at("created_at"),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index(
        "job_available",
        "job",
        ["tenant", "available_at"],
        postgresql_where=sa.text("claimed_at IS NULL"),
    )
    op.create_table(
        "outbox",
        _tenant(),
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        _at("created_at"),
        _at("published_at", nullable=True),
        sa.PrimaryKeyConstraint("tenant", "id"),
    )
    op.create_index(
        "outbox_unpublished",
        "outbox",
        ["tenant", "id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    # A runner claims a batch of due jobs for itself; a claimed row is invisible to every other
    # runner's claim, and a runner that dies mid-claim leaves nothing locked once its
    # transaction ends. The publisher claims unpublished outbox rows the same way. The
    # scheduler is a single instance elected by an advisory lock that lives as long as its
    # session (ADR-0002).
    op.execute(
        """
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
    )
    op.execute(
        """
        CREATE FUNCTION claim_outbox(batch integer) RETURNS SETOF outbox
        LANGUAGE sql AS $$
            SELECT * FROM outbox
            WHERE published_at IS NULL
            ORDER BY id
            LIMIT batch
            FOR UPDATE SKIP LOCKED
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION try_lead(role text) RETURNS boolean
        LANGUAGE sql AS $$
            SELECT pg_try_advisory_lock(hashtext('taktus.lead:' || role))
        $$
        """
    )

    # --- the application role ---------------------------------------------------------------
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT {ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON tenant TO {ROLE}")
    for table in TENANT_SCOPED:
        if table == "ledger_entry":
            op.execute(f"GRANT SELECT, INSERT ON ledger_entry TO {ROLE}")
        else:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION claim_jobs(text, integer), claim_outbox(integer), "
        f"try_lead(text) TO {ROLE}"
    )

    # --- row-level security: every table, forced, keyed on the session's tenant -------------
    for table in ("tenant", *TENANT_SCOPED):
        column = "id" if table == "tenant" else "tenant"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({column} = {CURRENT_TENANT}) WITH CHECK ({column} = {CURRENT_TENANT})"
        )


def downgrade() -> None:
    for table in reversed(("tenant", *TENANT_SCOPED)):
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    op.execute("DROP FUNCTION try_lead(text)")
    op.execute("DROP FUNCTION claim_outbox(integer)")
    op.execute("DROP FUNCTION claim_jobs(text, integer)")
    op.drop_table("outbox")
    op.drop_table("job")
    op.execute("DROP TRIGGER ledger_entry_no_truncate ON ledger_entry")
    op.execute("DROP TRIGGER ledger_entry_append_only ON ledger_entry")
    op.execute("DROP FUNCTION ledger_entry_is_append_only()")
    op.drop_table("ledger_entry")
    op.drop_table("artifact")
    op.drop_table("checkpoint")
    op.drop_table("step_run")
    op.drop_table("run")
    op.drop_table("plan")
    op.drop_table("command")
    op.drop_table("step")
    op.drop_table("process_version")
    op.drop_table("process")
    op.drop_table("tenant")
