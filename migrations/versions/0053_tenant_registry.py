"""The table `tenant` is read as the instance's registry (ADR-0104).

Revision: 0053
Revises: 0052

What this adds: one policy, no table and no column. The forced row-level security of revision
0001 lets a transaction see only the row of the tenant its setting `taktus.tenant` names. The
policy `tenant_registry` admits every row of `tenant` for reading, and only when the session
setting `taktus.registry` is `on`. The tenant store sets it in a transaction of its own, which
reads the registry and nothing else; a tenant's transaction that forgets a filter still sees its
own row alone. Policies of one table combine with OR, so the writes stay with
`tenant_isolation`. The previous release never sets `taktus.registry`, so it reads and writes
nothing differently because of it (ADR-0093).
"""

from __future__ import annotations

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

ROLE = "taktus_app"


def upgrade() -> None:
    op.execute(
        f"CREATE POLICY tenant_registry ON tenant FOR SELECT TO {ROLE} "
        "USING (current_setting('taktus.registry', true) = 'on')"
    )


def downgrade() -> None:
    op.execute("DROP POLICY tenant_registry ON tenant")
