# Docker

| File | Purpose |
|---|---|
| `compose.dev.yml` | the development database: PostgreSQL alone, bound to `127.0.0.1`, trusting local connections, its data in a named volume |

`make db-up` starts it and waits until it accepts connections; `make migrate` brings it to the
current schema (`TAKTUS_DATABASE_URL=postgresql://taktus@127.0.0.1:5432/taktus`); `make db-down`
stops it and keeps the volume. When port 5432 is taken on the machine, `TAKTUS_DB_PORT` picks
another host port, and the URL carries that port. Removing the volume is the operator's explicit act
(`docker volume rm taktus-dev-postgres`), never a make target: nothing here deletes data
without asking (CLAUDE.md §9).

The production shape — Taktus and PostgreSQL, two containers, all roles in one image
(ADR-0002) — arrives with the daemon. Until then, the application runs from a checkout
(`uv run taktusctl run …`) against this database or against the in-memory implementation.
Which one it uses is the first line of its output; neither is a silent default.
