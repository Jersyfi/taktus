# Migrations

Alembic, one directory, one head. `make migrate` brings the database named by
`TAKTUS_DATABASE_URL` to the current schema; the same happens in-process through
`taktus.adapters.driven.postgres.migrate` (the tests do that against a container).

| File | Holds |
|---|---|
| `alembic.ini` | Alembic's own configuration; no URL is in it |
| `env.py` | where the URL comes from — `TAKTUS_DATABASE_URL`, or the URL code hands over — and the adapter's metadata for drift checks |
| `versions/` | the history, one file per revision, explicit DDL |

The tables as the adapter queries them live in `src/taktus/adapters/driven/postgres/_schema.py`;
the migrations are the history that leads to them. `tests/adapters/persistence` fails when the
two disagree, so a change to the schema is a new revision plus the matching change to the
metadata — never a hand edit of an applied revision.

What the first revision decides — the tenant column and row-level security on every table, the
application role the adapter assumes, the append-only ledger, the queue and outbox that are
created but not yet used — is stated in its docstring, `versions/0001_first_schema.py`.

Rules:

- **A revision is never edited once it is on `main`.** A correction is the next revision.
- **The application connects as the user that ran the migration**, or as a member of the role
  `taktus_app` that the migration creates. The adapter assumes that role inside every
  transaction; a login that is not a member cannot open one.
- **Downgrades are potentially destructive** and follow CLAUDE.md §9: never without asking.
