"""Every insert into the ledger notifies, and a position is found from its hash (ADR-0055).

Revision: 0027
Revises: 0021

What this adds:

- `ledger_entry_notify()` and the trigger `ledger_entry_notifies`: after every statement that
  inserts into `ledger_entry`, one notification on the channel `taktus_ledger` per tenant the
  statement wrote, with the tenant as its payload and nothing else. A notification is
  delivered when the transaction commits; a transaction rolled back sends none. It is a signal
  that wakes a reader, never a record: what a reader receives is read from the ledger.
- `ledger_entry_hash`: an index from a tenant's entry hash to its sequence number. A reader's
  position is the hash of the last entry it received; this is how it is found again.

Nothing is dropped, and no row changes. The append-only triggers of revision 0001 stay as they
are; the new trigger only notifies.
"""

from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ledger_entry_hash", "ledger_entry", ["tenant", "hash"])
    op.execute(
        """
        CREATE FUNCTION ledger_entry_notify() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            written text;
        BEGIN
            FOR written IN SELECT DISTINCT tenant FROM inserted LOOP
                PERFORM pg_notify('taktus_ledger', written);
            END LOOP;
            RETURN NULL;
        END
        $$
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


def downgrade() -> None:
    # Potentially destructive: never without asking (CLAUDE.md §9).
    op.execute("DROP TRIGGER ledger_entry_notifies ON ledger_entry")
    op.execute("DROP FUNCTION ledger_entry_notify()")
    op.drop_index("ledger_entry_hash", table_name="ledger_entry")
