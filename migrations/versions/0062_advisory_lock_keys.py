"""A key per tenant for its advisory locks, and a namespace for the leadership lock (#317).

Revision: 0062
Revises: 0061

What this changes: `tenant.lock_key`, an integer the database assigns and keeps unique, so that
the ledger's advisory lock needs no hash of the tenant id: two tenants never share a key. And
`try_lead` takes its lock in the two-key form, in a namespace of its own, so that no tenant's
key can equal it. Every existing tenant receives a key.

The previous release still takes the one-key lock in `try_lead` and the ledger lock by hash. The
two forms exclude nobody from each other: during a rolling update an old and a new instance may
both lead or both append until the old ones are gone. The chain's primary key stays the
backstop for the ledger (ADR-0093).

ADR-0123 gives the reasons.
"""

from __future__ import annotations

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

LEADERSHIP = 1


def upgrade() -> None:
    op.execute("ALTER TABLE tenant ADD COLUMN lock_key integer GENERATED ALWAYS AS IDENTITY")
    op.execute("ALTER TABLE tenant ADD CONSTRAINT tenant_lock_key_unique UNIQUE (lock_key)")
    # The identity's sequence is new: the application role creates tenants and needs it.
    op.execute("GRANT USAGE ON SEQUENCE tenant_lock_key_seq TO taktus_app")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION try_lead(role text) RETURNS boolean
        LANGUAGE sql AS $$
            SELECT pg_try_advisory_lock({LEADERSHIP}, hashtext('taktus.lead:' || role))
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION try_lead(role text) RETURNS boolean
        LANGUAGE sql AS $$
            SELECT pg_try_advisory_lock(hashtext('taktus.lead:' || role))
        $$
        """
    )
    op.execute("ALTER TABLE tenant DROP CONSTRAINT tenant_lock_key_unique")
    op.execute("ALTER TABLE tenant DROP COLUMN lock_key")
