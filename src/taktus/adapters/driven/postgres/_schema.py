"""The tables, as SQLAlchemy Core metadata: what the adapter's statements are written against.

The migrations under `migrations/` create the same tables with explicit DDL; this module is the
current shape, the migrations are the history. `tests/adapters/persistence` compares the two and
fails on any drift. Everything the database enforces beyond columns — row-level security, the
append-only ledger, the immutable provenance, the claiming functions, the application role —
lives in the migrations alone, because it is not part of a statement's shape.

Rules the layout follows:

- every table carries `tenant` (ADR-0020), and every primary key starts with it;
- a foreign key never crosses a component boundary (ADR-0016): `run` names its plan by id,
  `plan` its command, `process_version` its process — but nothing in the database ties them,
  so that a component's data can move to a store of its own without a migration elsewhere;
- inside an aggregate, children hang off their parent with `ON DELETE CASCADE` and are replaced
  with it;
- what is a *copy* is stored as a document: the steps of a plan and of a run are copies of the
  process version's steps, kept so that the run can be replayed from its own record, and are
  JSON columns; the process version's own steps are rows, because they are the source.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()


def _tenant() -> Column[str]:
    return Column("tenant", Text, ForeignKey("tenant.id"), nullable=False)


def _at(name: str, *, nullable: bool = False) -> Column[datetime]:
    return Column(name, DateTime(timezone=True), nullable=nullable)


tenant = Table(
    "tenant",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    _at("created_at"),
)

# --- process ------------------------------------------------------------------------------------

process = Table(
    "process",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text),
    Column("active_version", Text),
    Column("activated_by", Text),
    _at("activated_at", nullable=True),  # ADR-0048 §6
    PrimaryKeyConstraint("tenant", "id"),
)

process_version = Table(
    "process_version",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # process_id@version, how the ledger names it
    Column("process_id", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("autonomy_level", Integer, nullable=False),  # the level alone, for a query
    Column("autonomy", JSONB, nullable=False),  # level, reason, toward_next (ADR-0026)
    Column("triggers", JSONB, nullable=False),
    Column("slo", JSONB),
    Column("work", JSONB, nullable=False),
    Column("limits", JSONB),
    Column("inputs", JSONB, nullable=False),
    Column("author", Text),
    Column("reason", Text),
    PrimaryKeyConstraint("tenant", "id"),
    UniqueConstraint("tenant", "process_id", "version", name="process_version_unique"),
)

# --- identity -----------------------------------------------------------------------------------

identity_table = Table(
    "identity",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("org_path", JSONB, nullable=False),
    Column("roles", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("key_digest", Text),
    _at("created_at"),
    PrimaryKeyConstraint("tenant", "id"),
)

channel_link = Table(
    "channel_link",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # derived from channel and account: one per account
    Column("channel", Text, nullable=False),
    Column("account", Text, nullable=False),
    Column("identity", Text, nullable=False),
    Column("origin", Text, nullable=False),
    _at("linked_at"),
    _at("revoked_at", nullable=True),
    Column("revoked_by", Text),
    PrimaryKeyConstraint("tenant", "id"),
)

link_code = Table(
    "link_code",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # the digest of the code; the code is kept nowhere
    Column("identity", Text, nullable=False),
    Column("channel", Text, nullable=False),
    _at("created_at"),
    _at("expires_at"),
    _at("used_at", nullable=True),
    PrimaryKeyConstraint("tenant", "id"),
)

# --- anchors and decisions (ADR-0042) -------------------------------------------------------------

anchor_configuration = Table(
    "anchor_configuration",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # the tenant: one configuration each
    Column("anchors", JSONB, nullable=False),
    Column("risk_classes", JSONB, nullable=False),
    _at("configured_at", nullable=True),
    Column("configured_by", Text),
    PrimaryKeyConstraint("tenant", "id"),
)

decision_request = Table(
    "decision_request",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("decider", Text, nullable=False),  # a role, never a person
    Column("anchor", Text),
    Column("status", Text, nullable=False),
    Column("run_id", Text, nullable=False),
    _at("raised_at"),
    Column("request", JSONB, nullable=False),  # DecisionRequest.json
    Column("answered_by", Text),
    _at("answered_at", nullable=True),
    Column("reflection", Text),
    Column("decided_by", Text),
    _at("decided_at", nullable=True),
    PrimaryKeyConstraint("tenant", "id"),
    Index("decision_request_status", "tenant", "status"),
)

register_entry = Table(
    "register_entry",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("request_id", Text, nullable=False),
    Column("run_id", Text, nullable=False),
    Column("step_id", Text, nullable=False),
    Column("entry", JSONB, nullable=False),
    _at("decided_at"),
    PrimaryKeyConstraint("tenant", "id"),
)

owner_channel = Table(
    "owner_channel",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # the tenant: one channel each
    Column("channel", JSONB, nullable=False),
    _at("configured_at"),
    PrimaryKeyConstraint("tenant", "id"),
)

report = Table(
    "report",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("due", Date, nullable=False),
    _at("raised_at"),
    Column("report", JSONB, nullable=False),
    PrimaryKeyConstraint("tenant", "id"),
    Index("report_state", "tenant", "state"),
)

trigger_state = Table(
    "trigger_state",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # <process>:<trigger key>
    Column("process_id", Text, nullable=False),
    Column("schedule", Text, nullable=False),
    _at("armed_at"),
    _at("fired_slot", nullable=True),
    _at("fired_at", nullable=True),
    Column("runs", JSONB, nullable=False),
    PrimaryKeyConstraint("tenant", "id"),
)

step = Table(
    "step",
    metadata,
    _tenant(),
    Column("version_id", Text, nullable=False),
    Column("id", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Column("method", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("rejected", JSONB, nullable=False),
    Column("exactness", Text),
    Column("checks", JSONB),
    Column("fallback", JSONB),
    Column("model", Text),
    Column("requires", JSONB),
    Column("depends_on", JSONB),
    PrimaryKeyConstraint("tenant", "version_id", "id"),
    ForeignKeyConstraint(
        ["tenant", "version_id"],
        ["process_version.tenant", "process_version.id"],
        ondelete="CASCADE",
        name="step_version",
    ),
)

# --- command --------------------------------------------------------------------------------------

command = Table(
    "command",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("channel", Text, nullable=False),
    Column("identity", Text, nullable=False),
    Column("org_path", JSONB, nullable=False),
    Column("intent", JSONB, nullable=False),
    Column("context", JSONB),
    Column("reply_to", JSONB, nullable=False),
    _at("received_at"),
    PrimaryKeyConstraint("tenant", "id"),
)

intake_event = Table(
    "intake_event",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # the source system's delivery identifier
    Column("channel", Text, nullable=False),
    Column("event", Text, nullable=False),
    Column("sender_account", Text, nullable=False),
    Column("sender_kind", Text, nullable=False),
    Column("intent", Text, nullable=False),
    Column("context", JSONB, nullable=False),
    Column("reply_channel", Text, nullable=False),
    Column("reply_address", Text, nullable=False),
    Column("reply_thread", Text),
    _at("occurred_at"),
    _at("received_at"),
    Column("status", Text, nullable=False),
    Column("command_id", Text),  # set when completed: the command this event became
    _at("completed_at", nullable=True),
    PrimaryKeyConstraint("tenant", "id"),
    Index("intake_event_received", "tenant", "received_at"),
)

plan = Table(
    "plan",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("command_id", Text, nullable=False),
    Column("goal", Text, nullable=False),
    Column("autonomy_level", Integer, nullable=False),
    _at("due", nullable=True),
    Column("steps", JSONB, nullable=False),
    Column("results_in", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("commissioned_by", Text),
    _at("commissioned_at", nullable=True),
    PrimaryKeyConstraint("tenant", "id"),
)

# --- catalog --------------------------------------------------------------------------------------

adapter_maturity = Table(
    "adapter_maturity",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),  # the adapter identifier, never a product name
    Column("family", Text, nullable=False),
    _at("conformance_passed_at", nullable=True),  # when the last conformance run passed
    Column("conformance", JSONB),  # the last conformance run, as its document (ADR-0044)
    Column("removal", JSONB),  # the last removal result, as its document
    _at("updated_at"),
    PrimaryKeyConstraint("tenant", "id"),
)

# --- run ------------------------------------------------------------------------------------------

run = Table(
    "run",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("plan_id", Text, nullable=False),
    Column("process_version", Text, nullable=False),
    Column("identity", Text, nullable=False),
    Column("autonomy_level", Integer, nullable=False),
    Column("budget", JSONB, nullable=False),
    Column("margin", Float, nullable=False, server_default="0"),
    Column("steps", JSONB, nullable=False),
    Column("work", JSONB, nullable=False),
    Column("inputs", JSONB, nullable=False),
    Column("rehearsal", Boolean, nullable=False),  # ADR-0030
    Column("actions", JSONB, nullable=False, server_default=text("'{}'::jsonb")),  # ADR-0039
    Column("state", Text, nullable=False),
    Column("cause", Text),
    Column("reason", Text),
    _at("created_at"),
    _at("updated_at"),
    PrimaryKeyConstraint("tenant", "id"),
    Index("run_state", "tenant", "state"),
)

step_run = Table(
    "step_run",
    metadata,
    _tenant(),
    Column("run_id", Text, nullable=False),
    Column("step_id", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Column("method", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("retryable", Boolean),
    Column("adapter", Text),
    Column("assignment_id", Text),
    Column("assignment_open", Boolean, nullable=False, server_default=text("false")),  # ADR-0038
    Column("assignment_seq", Integer, nullable=False, server_default=text("0")),
    Column("estimate", JSONB),
    Column("reservation", JSONB),
    Column("consumption", JSONB),
    Column("reason", Text),
    _at("started_at", nullable=True),
    _at("finished_at", nullable=True),
    _at("waiting_since", nullable=True),  # ADR-0037
    Column("waits", Integer, nullable=False, server_default=text("0")),
    Column("confirmed_by", Text),  # ADR-0039
    Column("block", JSONB),  # ADR-0043
    Column("anchoring", JSONB),  # ADR-0042
    PrimaryKeyConstraint("tenant", "run_id", "step_id"),
    ForeignKeyConstraint(
        ["tenant", "run_id"], ["run.tenant", "run.id"], ondelete="CASCADE", name="step_run_run"
    ),
)

checkpoint = Table(
    "checkpoint",
    metadata,
    _tenant(),
    Column("run_id", Text, nullable=False),
    Column("step_id", Text, nullable=False),
    Column("ref", Text, nullable=False),
    _at("taken_at"),
    Column("artifact_ids", JSONB, nullable=False),
    Column("result_digest", Text),
    PrimaryKeyConstraint("tenant", "run_id", "step_id"),
    ForeignKeyConstraint(
        ["tenant", "run_id", "step_id"],
        ["step_run.tenant", "step_run.run_id", "step_run.step_id"],
        ondelete="CASCADE",
        name="checkpoint_step_run",
    ),
)

artifact = Table(
    "artifact",
    metadata,
    _tenant(),
    Column("run_id", Text, nullable=False),
    Column("step_id", Text, nullable=False),
    Column("id", Text, nullable=False),
    Column("position", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("digest", Text, nullable=False),
    Column("media_type", Text),
    Column("size_bytes", BigInteger),
    Column("uri", Text),
    Column("title", Text),
    _at("created_at", nullable=True),
    PrimaryKeyConstraint("tenant", "run_id", "step_id", "id"),
    ForeignKeyConstraint(
        ["tenant", "run_id", "step_id"],
        ["step_run.tenant", "step_run.run_id", "step_run.step_id"],
        ondelete="CASCADE",
        name="artifact_step_run",
    ),
)

# --- ledger ---------------------------------------------------------------------------------------

ledger_entry = Table(
    "ledger_entry",
    metadata,
    _tenant(),
    Column("seq", BigInteger, nullable=False),
    _at("ts"),
    Column("kind", Text, nullable=False),
    Column("prev_hash", Text),
    Column("hash", Text, nullable=False),
    Column("refs", JSONB, nullable=False),
    Column("method", Text),
    Column("model", Text),
    Column("adapter", Text),
    Column("consumption", JSONB),
    Column("outcome", Text),
    Column("content_digest", Text),
    Column("rehearsal", Boolean),  # true on every entry of a rehearsal run (ADR-0030)
    PrimaryKeyConstraint("tenant", "seq"),
    Index("ledger_entry_run", "tenant", text("(refs ->> 'run_id')")),
    # A reader's position is an entry's hash; this finds its sequence number (ADR-0055 §4).
    Index("ledger_entry_hash", "tenant", "hash"),
)

LEDGER_CHANNEL = "taktus_ledger"
"""The notification channel every insert into `ledger_entry` notifies, with the tenant as its
payload, from a statement-level trigger (migration 0027, ADR-0055 §2)."""

# --- provenance (ADR-0021) ------------------------------------------------------------------------

provenance = Table(
    "provenance",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("run_id", Text, nullable=False),
    Column("step_id", Text, nullable=False),
    Column("process_version", Text, nullable=False),
    Column("method", Text, nullable=False),
    Column("exactness", Text),
    Column("model", Text),
    Column("prompt", Text),
    Column("adapter", Text),
    Column("adapter_version", Text),
    Column("inputs", JSONB, nullable=False),
    Column("outputs", JSONB, nullable=False),
    Column("result_digest", Text),
    Column("ledger_seq", BigInteger, nullable=False),
    _at("recorded_at"),
    PrimaryKeyConstraint("tenant", "id"),
    UniqueConstraint("tenant", "run_id", "step_id", name="provenance_once_per_step_run"),
    Index("provenance_run", "tenant", "run_id"),
)

# --- queue and outbox (ADR-0002) — created now, used from the daemon on --------------------

job = Table(
    "job",
    metadata,
    _tenant(),
    Column("id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    _at("available_at"),
    _at("claimed_at", nullable=True),
    Column("claimed_by", Text),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("deferrals", Integer, nullable=False, server_default=text("0")),  # ADR-0037
    _at("created_at"),
    PrimaryKeyConstraint("tenant", "id"),
    Index(
        "job_available",
        "tenant",
        "available_at",
        postgresql_where=text("claimed_at IS NULL"),
    ),
)

outbox = Table(
    "outbox",
    metadata,
    _tenant(),
    Column("id", BigInteger, Identity(always=True), nullable=False),
    Column("topic", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    _at("created_at"),
    _at("published_at", nullable=True),
    PrimaryKeyConstraint("tenant", "id"),
    Index("outbox_unpublished", "tenant", "id", postgresql_where=text("published_at IS NULL")),
)

# Every table the application touches, for the grants and the row-level security policies.
TENANT_SCOPED: tuple[Table, ...] = (
    process,
    process_version,
    step,
    command,
    intake_event,
    plan,
    run,
    step_run,
    checkpoint,
    artifact,
    ledger_entry,
    provenance,
    job,
    outbox,
)

APPLICATION_ROLE = "taktus_app"
"""The role the adapter assumes inside every transaction (`SET LOCAL ROLE`). It owns nothing,
cannot log in, sees only the tenant the transaction names, and may not update or delete a
ledger entry or a provenance record. The migrations create it and grant it to the user running
them."""

TENANT_SETTING = "taktus.tenant"
"""The session setting the row-level security policies read: `current_setting('taktus.tenant')`.
Unset, no row is visible."""
