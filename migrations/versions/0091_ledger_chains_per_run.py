"""A chain per run, anchored in the tenant's chain, and the ledger partitioned by time
(ADR-0164, issue #341).

Revision: 0091
Revises: 0090

What this changes:

- `ledger_entry.chain_seq`, the entry's place in its chain; `ledger_entry.chain`, `tenant` on an
  entry that references a run and is on the tenant's chain all the same; `ledger_entry.through`,
  the bound an anchor covers; and `ledger_entry.on_chain`, the chain's name as the store finds it
  — the run's identifier, or empty for the tenant's chain. Every entry stored before keeps what
  it has: null in the first three, empty in the last. It is on the tenant's chain, where its
  place is its sequence number. No stored entry is rewritten.
- The sequence `ledger_entry_seq`, which hands out the reading positions from above every
  stored one, and the function `ledger_allocate(tenant)`, which takes the next position and
  marks the transaction as holding the stable head below it (ADR-0164 §3).
- `ledger_entry` becomes a table partitioned by month of `ts`. The table as it was becomes its
  first partition, `ledger_entry_before`, covering everything up to the month after the newest
  entry; no row is copied, moved or deleted. A partition per month follows, created ahead by
  `ledger_partitions(months)`, and a default partition catches an entry no month covers. The
  primary key gains `ts`, which a partitioned table's key must contain.
- The guards move to the partitioned table: the append-only trigger rejects every update and
  delete on every partition, each partition rejects a truncate, the insert notifies as before.
  Row-level security and the application role's rights stand on the partitioned table.

The migration narrows what the previous build relies on: the primary key changes, and the
previous build chains every entry to the tenant's newest under one lock, which would interleave
with the chains this build writes. `taktus_oldest_code()` therefore names this revision: an
older build is not ready against this schema (ADR-0093 §1).
"""

from __future__ import annotations

from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

ROLE = "taktus_app"
CURRENT_TENANT = "NULLIF(current_setting('taktus.tenant', true), '')"

CHAIN = "(tenant, on_chain, seq)"
INDEXES = {
    "ledger_entry_run": "(tenant, (refs ->> 'run_id'))",
    "ledger_entry_process": "(tenant, (split_part(refs ->> 'process_version', '@', 1)), kind, ts)",
    "ledger_entry_hash": "(tenant, hash)",
    "ledger_entry_kind": "(tenant, kind, seq)",
    "ledger_entry_kind_ts": "(tenant, kind, ts)",
}


def _quoted(sql: str) -> str:
    """A statement's text inside a string literal of SQL."""
    return sql.replace("'", "''")


def upgrade() -> None:
    op.execute("ALTER TABLE ledger_entry ADD COLUMN chain_seq bigint")
    op.execute("ALTER TABLE ledger_entry ADD COLUMN chain text")
    op.execute("ALTER TABLE ledger_entry ADD COLUMN through bigint")
    op.execute("ALTER TABLE ledger_entry ADD COLUMN on_chain text NOT NULL DEFAULT ''")

    # --- the table as it was becomes the first partition ------------------------------------
    op.execute("ALTER TABLE ledger_entry RENAME TO ledger_entry_before")
    # The key a partition of a table partitioned by `ts` must carry. Every stored key stays
    # unique: (tenant, seq) was, so (tenant, seq, ts) is.
    op.execute("ALTER TABLE ledger_entry_before DROP CONSTRAINT ledger_entry_pkey")
    op.execute(
        "ALTER TABLE ledger_entry_before ADD CONSTRAINT ledger_entry_before_pkey "
        "PRIMARY KEY (tenant, seq, ts)"
    )
    # A partition's index is named after the partitioned table's, with the partition's
    # suffix, so that a plan names the index it reads by (ADR-0105).
    for name in INDEXES:
        op.execute(f"ALTER INDEX {name} RENAME TO {name}_before")
    op.execute(
        "CREATE INDEX ledger_entry_chain_before ON ledger_entry_before (tenant, on_chain, seq)"
    )
    # The row trigger and the notification move to the partitioned table; the truncate guard
    # stays on the partition, where a truncate would be aimed.
    op.execute("DROP TRIGGER ledger_entry_append_only ON ledger_entry_before")
    op.execute("DROP TRIGGER ledger_entry_notifies ON ledger_entry_before")
    op.execute("DROP POLICY tenant_isolation ON ledger_entry_before")
    op.execute(f"REVOKE ALL ON ledger_entry_before FROM {ROLE}")

    op.execute(
        """
        CREATE TABLE ledger_entry (
            LIKE ledger_entry_before INCLUDING DEFAULTS
        ) PARTITION BY RANGE (ts)
        """
    )
    op.execute(
        "ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_tenant_fkey "
        "FOREIGN KEY (tenant) REFERENCES tenant (id)"
    )
    op.execute(
        "ALTER TABLE ledger_entry ADD CONSTRAINT ledger_entry_pkey PRIMARY KEY (tenant, seq, ts)"
    )
    for name, columns in INDEXES.items():
        op.execute(f"CREATE INDEX {name} ON ledger_entry {columns}")
    # The newest entry of a chain, and a place in it (ADR-0164).
    op.execute(f"CREATE INDEX ledger_entry_chain ON ledger_entry {CHAIN}")
    op.execute(
        """
        DO $$
        DECLARE
            bound timestamptz := date_trunc(
                'month', greatest(now(), (SELECT max(ts) FROM ledger_entry_before))
            ) + interval '1 month';
        BEGIN
            EXECUTE format(
                'ALTER TABLE ledger_entry ATTACH PARTITION ledger_entry_before '
                'FOR VALUES FROM (MINVALUE) TO (%L)', bound
            );
        END
        $$
        """
    )
    # What a partition made after this one carries, under its own names (ADR-0105).
    indexed = "".join(
        f"EXECUTE format('CREATE INDEX %I ON %I {_quoted(columns)}', '{name}_' || suffix, "
        "partition);\n"
        for name, columns in {**INDEXES, "ledger_entry_chain": CHAIN}.items()
    )
    op.execute(
        f"""
        CREATE FUNCTION ledger_partition_made(partition text, suffix text) RETURNS void
        LANGUAGE plpgsql SET search_path = public AS $$
        BEGIN
            {indexed}
            EXECUTE format(
                'CREATE TRIGGER ledger_entry_no_truncate BEFORE TRUNCATE ON %I '
                'FOR EACH STATEMENT EXECUTE FUNCTION ledger_entry_is_append_only()',
                partition
            );
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ledger_partition_made(text, text) FROM PUBLIC")
    op.execute("CREATE TABLE ledger_entry_later (LIKE ledger_entry INCLUDING DEFAULTS)")
    op.execute("SELECT ledger_partition_made('ledger_entry_later', 'later')")
    op.execute("ALTER TABLE ledger_entry ATTACH PARTITION ledger_entry_later DEFAULT")
    op.execute(
        """
        CREATE TRIGGER ledger_entry_append_only
        BEFORE UPDATE OR DELETE ON ledger_entry
        FOR EACH ROW EXECUTE FUNCTION ledger_entry_is_append_only()
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_entry_notifies
        AFTER INSERT ON ledger_entry
        REFERENCING NEW TABLE AS inserted
        FOR EACH STATEMENT EXECUTE FUNCTION ledger_entry_notify()
        """
    )
    op.execute("ALTER TABLE ledger_entry ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ledger_entry FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON ledger_entry "
        f"USING (tenant = {CURRENT_TENANT}) WITH CHECK (tenant = {CURRENT_TENANT})"
    )
    op.execute(f"GRANT SELECT, INSERT ON ledger_entry TO {ROLE}")

    # --- a partition per month, created ahead ----------------------------------------------
    # SECURITY DEFINER: the application role creates no table of its own; it asks for the
    # months ahead, and the function, owned by whoever migrates, creates them.
    op.execute(
        """
        CREATE FUNCTION ledger_partitions(months integer) RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
        DECLARE
            month timestamptz := (
                SELECT max(upper_bound) FROM (
                    SELECT (regexp_match(
                        pg_get_expr(c.relpartbound, c.oid), 'TO \\(''([^'']+)''\\)'
                    ))[1]::timestamptz AS upper_bound
                    FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                    WHERE i.inhparent = 'ledger_entry'::regclass
                ) bounds
            );
            until timestamptz := date_trunc('month', now()) + make_interval(months => months);
            made integer := 0;
            name text;
        BEGIN
            WHILE month < until LOOP
                name := 'ledger_entry_' || to_char(month AT TIME ZONE 'UTC', 'YYYY_MM');
                BEGIN
                    EXECUTE format(
                        'CREATE TABLE %I (LIKE ledger_entry INCLUDING DEFAULTS)', name
                    );
                    PERFORM ledger_partition_made(
                        name, to_char(month AT TIME ZONE 'UTC', 'YYYY_MM')
                    );
                    EXECUTE format(
                        'ALTER TABLE ledger_entry ATTACH PARTITION %I '
                        'FOR VALUES FROM (%L) TO (%L)',
                        name, month, month + interval '1 month'
                    );
                    made := made + 1;
                EXCEPTION WHEN check_violation THEN
                    -- The default partition already holds an entry of that month. It stays
                    -- there: nothing of the ledger is moved, and no later month is made.
                    RAISE NOTICE 'ledger partition % not made: the default partition holds '
                        'entries of its month', name;
                    RETURN made;
                END;
                month := month + interval '1 month';
            END LOOP;
            RETURN made;
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION ledger_partitions(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION ledger_partitions(integer) TO {ROLE}")
    op.execute("SELECT ledger_partitions(3)")

    # --- the reading positions ---------------------------------------------------------------
    op.execute("CREATE SEQUENCE ledger_entry_seq AS bigint MINVALUE 1 CACHE 1")
    op.execute(
        "SELECT setval('ledger_entry_seq', (SELECT coalesce(max(seq), 0) + 1 FROM ledger_entry), "
        "false)"
    )
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE ledger_entry_seq TO {ROLE}")
    # The marker is taken before the position, and its key is a bound below the position: the
    # sequence's last value as read before `nextval`. A reader that finds the marker knows
    # every position this transaction holds lies above it (ADR-0164 §3). It is taken once per
    # transaction and tenant: the first position is the lowest.
    op.execute(
        """
        CREATE FUNCTION ledger_allocate(tenant_id text) RETURNS bigint
        LANGUAGE plpgsql AS $$
        DECLARE
            key integer := (SELECT lock_key FROM tenant WHERE id = tenant_id);
            below bigint;
        BEGIN
            IF current_setting('taktus.ledger_open_' || key, true) IS DISTINCT FROM 'on' THEN
                SELECT CASE WHEN is_called THEN last_value ELSE last_value - 1 END
                    INTO below FROM ledger_entry_seq;
                PERFORM pg_advisory_xact_lock_shared(~((key::bigint << 40) | below));
                PERFORM set_config('taktus.ledger_open_' || key, 'on', true);
            END IF;
            RETURN nextval('ledger_entry_seq');
        END
        $$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION ledger_allocate(text) TO {ROLE}")
    # The stable head below the open markers of other transactions: what `head` reads.
    op.execute(
        """
        CREATE FUNCTION ledger_open_below(tenant_id text) RETURNS bigint
        LANGUAGE sql VOLATILE AS $$
            SELECT min(~marker & ((1::bigint << 40) - 1))
            FROM (
                SELECT (l.classid::bigint << 32) | l.objid::bigint AS marker
                FROM pg_locks l
                WHERE l.locktype = 'advisory' AND l.objsubid = 1
                  AND l.pid <> pg_backend_pid()
            ) held
            WHERE marker < 0
              AND (~marker >> 40) = (SELECT lock_key FROM tenant WHERE id = tenant_id)
        $$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION ledger_open_below(text) TO {ROLE}")

    op.execute(
        "CREATE OR REPLACE FUNCTION taktus_oldest_code() RETURNS text "
        "LANGUAGE sql IMMUTABLE AS $$ SELECT '0091'::text $$"
    )


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9). Every entry written since
    # has a place in a run's chain that the previous rule cannot read, so there is no way back
    # that keeps the chains verifying; restore the backup taken before the migration instead.
    raise NotImplementedError("migration 0091 is not reversed; restore the earlier backup")
