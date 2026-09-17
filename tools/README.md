# Tools

Repository tooling. Nothing here is part of the product.

| Tool | Runs as | Does |
|---|---|---|
| `validate_contracts.py` | `make gate-contracts` | every schema under `contracts/` is valid JSON Schema 2020-12, carries the `$id` its path prescribes (ADR-0019) and has resolvable `$ref`s; every `openapi.yaml` is 3.1 with resolvable `$ref`s; every example validates; every must-fail example fails by schema — except transcripts, which must be schema-valid and whose stream rule `tests/conformance` checks; every conformance check W-01..W-13 and C-01..C-10 has a fixture |
| `check_decisions.py` | `make gate-decisions` | every request under `docs/decisions/open/` has the header and the seven sections, none empty, no placeholder, one recommended option; every record under `docs/decisions/` has an `## Outcome` with a date and an answer and is listed in the index; no number is both open and recorded; with `--pr-body` and `--draft` (CI): every decision the pull request names has its file, every BLOCKING file is named, and a BLOCKING decision keeps the pull request a draft; with `--forbid-open-blocking` (main): no BLOCKING file is open |
| `checkdocs.py` | `make gate-docs` | a change to a contract, a tool, a make target, the architecture contracts, a component, a port, an adapter, the composition root, a wire format, a worker, a blueprint, an example or a deployment touches the documentation of that place in the same change; compares with `origin/main` (or `BASE=<ref>`); nothing changed, or nothing that a rule covers, is green |
| `gate.py` | `make test`, `make gate-arch`, `-conformance`, `-governance`, `-exactness` | runs pytest on one directory; "no tests collected" reports "no targets yet" and green, every other exit code passes through. `gate-conformance` starts the reference worker, the reference connector and the fake of its service as processes from the tests themselves |
| `preflight.sh` | every make target, through `need-<tool>`; `make doctor` | a missing tool names itself, what it is for and the one command that installs it, instead of `make: uv: No such file or directory`; `make doctor` reports two levels — the system tools (`uv`, `gitleaks`; `docker` and `node` optional), and the project environment with the tools the gates actually invoke through `uv run` (ruff, mypy, pytest, lint-imports, taktusctl) — says which is incomplete, and exits non-zero if either is |
| `generate.py` | `make generate` | writes `api/openapi.yaml` from the FastAPI application (`src/taktus/adapters/driving/rest`), built at the root with the path prefix as a server variable; the file is committed and `tests/adapters/rest/test_openapi.py` fails when it is out of date. The shared kernel is a checked binding, not generated (`docs/architecture/project-structure.md` §4) |

`validate_contracts.py` carries its own dependencies in a PEP 723 header, so `uv run
tools/validate_contracts.py` works without the project installed. A third party can check a contract
with nothing but that file. `check_decisions.py` and `checkdocs.py` use the standard library only
and run the same way; CI runs the first two without `make install`.

**A gate with nothing to check reports green and says so.** A gate that is red because it found
nothing is broken, not strict. `make gates` needs `uv` and `gitleaks` on the path, and nothing else
— no Node, no database, and no `make install` first. The tests that need PostgreSQL bring their
own through Docker and skip with the reason when Docker is absent; in CI `TAKTUS_REQUIRE_DATABASE`
turns that skip into a failure, so that the gate cannot go green by not looking. Every target that runs a tool from the
project environment depends on `env`, which syncs the environment once when `pyproject.toml` or
`uv.lock` is newer than its stamp (`.venv/.synced`) or the environment is absent; a fresh clone
is green in one command. `make doctor` says which of the two levels is present; Node is listed
as optional, for the web targets that will need it. CI reaches the same preflight through
`need-<tool>` on every target it runs, so it does not call `make doctor` (its secret scan runs
through an action that brings its own `gitleaks`).

Six targets are for operating and not gates. `make up` brings Taktus up in two containers
(`deploy/docker/compose.yml`: writes the secret files once, builds the image, applies the
migrations, waits for readiness), `make down` stops them and keeps every volume, and
`make verify-compose` runs `deploy/docker/verify.sh` — from nothing to a run that survives a
killed container. `make db-up` and `make db-down` start and stop the development database
(`deploy/docker/compose.dev.yml`; `db-down` keeps the volume), and `make migrate` runs the
Alembic migrations against `TAKTUS_DATABASE_URL_FILE` or `TAKTUS_DATABASE_URL`. All six need
`docker` except `migrate`.

**A gate that cannot run says why.** An unclear message is a defect, not a minor annoyance —
the same rule ADR-0017 applies to decision requests, applied to tooling.
