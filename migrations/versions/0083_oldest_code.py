"""The schema names the oldest build that runs against it (ADR-0093 §2, #330).

Revision: 0083
Revises: 0074

What this adds: the function `taktus_oldest_code()`, which returns the head revision of the
oldest build of Taktus the schema still serves. A build that finds the database at a revision
it does not know — a newer build migrated it — stays ready while that build is the one named or
a later one (`adapters/driven/postgres/migrate.py`, `check_schema`).

It names 0074: this migration only adds a function, and the build whose head is 0074 runs
against it unchanged. A later migration that only expands leaves the function as it is. One
that contracts — drops, renames or narrows what an older build reads — replaces it with its own
revision, and says so in its docstring (ADR-0093 §1).

No table, so no tenant and no row-level security: the function holds a constant and reads
nothing. Every role may call it, as it may read `alembic_version`. The previous release neither
reads nor calls it (ADR-0093).
"""

from __future__ import annotations

from alembic import op

revision = "0083"
down_revision = "0074"
branch_labels = None
depends_on = None

OLDEST_CODE = "0074"
"""The head revision of the oldest build this schema serves."""


def upgrade() -> None:
    op.execute(
        "CREATE OR REPLACE FUNCTION taktus_oldest_code() RETURNS text "
        f"LANGUAGE sql IMMUTABLE AS $$ SELECT '{OLDEST_CODE}'::text $$"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION taktus_oldest_code()")
