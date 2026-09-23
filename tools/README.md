# Tools

Repository tooling. Nothing here is part of the product.

| Tool | Runs as | Does |
|---|---|---|
| `validate_contracts.py` | `make gate-contracts` | every schema under `contracts/` is valid JSON Schema 2020-12, carries the `$id` its path prescribes (ADR-0019) and has resolvable `$ref`s; every `openapi.yaml` is 3.1 with resolvable `$ref`s; every example validates; every must-fail example fails by schema — except transcripts, which must be schema-valid and whose stream rule `tests/conformance` checks; every conformance check W-01..W-13 and C-01..C-10 has a fixture |
| `check_decisions.py` | `make gate-decisions` | every request under `docs/decisions/open/` has the header and the seven sections, none empty, no placeholder, one recommended option; every record under `docs/decisions/` has an `## Outcome` with a date and an answer and is listed in the index; no number is both open and recorded; every notice `NTC-NNNN` has a mode-2 entry that `anchors.taktus.md` defines, the kind that entry names there, a date, the pull request, its four sections and — for the kind `gate-weakened` — the demonstration that the gate had no value, naming the gate, and is listed in the index; every needs request `NEED-NNNN` (ADR-0028) has a kind from the vocabulary, an issue, a date, the pull request it became foreseeable in, its seven sections in order with no placeholder, section 5 saying what it must never be, and — once provided — an `## Outcome` with the date and the check, listed in the index; every row of `CREDENTIALS.md` names a needs request that has a file or `none` with a reason, and every `<NAME>_FILE` variable the code names is described there; with `--pr-body` and `--draft` (CI): every decision the pull request names has its file, every BLOCKING file is named, and a BLOCKING decision keeps the pull request a draft; with `--forbid-open-blocking` (main): no BLOCKING file is open |
| `check_adrs.py` | `make gate-adrs` | every ADR under `docs/adr/` has its title and status and is listed in the index; every ADR whose prose makes a promise — "never", "always", "guarantee", "immutable", "at most", "exactly", "cannot", "must" — carries `## Where this promise ends` as its last section, with at least three sentences, no placeholder and not a bare pointer; an ADR without a promise marker may omit it and is reported as such |
| `check_status.py` | `make gate-status`; `make generate` (with `--write`) | `docs/status.md` — the one file that says where the project stands and what is needed from the owner (ADR-0028) — starts with `# Status`, carries `**As of:**` with a date, and has its five sections in order, none empty, no placeholder; the milestone section 1 names is a milestone heading of `docs/roadmap.md`; the date is not older than the newest record of the register; the generated block of section 3 is what `docs/decisions/open/` generates now — every open need and decision request, the most urgent first (`--write` writes it); against `origin/main` (or `BASE=<ref>`) a change under `src/`, `workers/`, `blueprints/`, `contracts/`, `deploy/`, `migrations/`, `tools/`, `docs/adr/`, `docs/decisions/` or to `docs/roadmap.md` comes with a change to `docs/status.md`; with `--pr-body` (CI): the description's last section `## Needed from the owner` is that block |
| `checkdocs.py` | `make gate-docs` | a change to a contract, a tool, a make target, the architecture contracts, a component, a port, an adapter, the composition root, a wire format, a worker, a blueprint, an example or a deployment touches the documentation of that place in the same change; compares with `origin/main` (or `BASE=<ref>`); nothing changed, or nothing that a rule covers, is green |
| `gate.py` | `make test`, `make gate-arch`, `-conformance`, `-governance`, `-exactness` | runs pytest on one directory; "no tests collected" reports "no targets yet" and green, every other exit code passes through; prints the gate's duration as its last line, so that a suite grown too slow is reported with its cost before and after (CLAUDE.md §11) from the logs, not from memory. `gate-conformance` starts the reference worker, the reference connector and the fake of its service as processes from the tests themselves |
| `preflight.sh` | every make target, through `need-<tool>`; `make doctor` | a missing tool names itself, what it is for and the one command that installs it, instead of `make: uv: No such file or directory`; `make doctor` reports two levels — the system tools (`uv`, `gitleaks`; `docker` and `node` optional), and the project environment with the tools the gates actually invoke through `uv run` (ruff, mypy, pytest, lint-imports, taktusctl) — says which is incomplete, and exits non-zero if either is |
| `first_run.sh` | `tools/first_run.sh <issue>` | the first end-to-end in one command: starts the reference connector against the repository this checkout was cloned from and the coding worker by endpoint, runs P-02 Refinement and then P-03 Implementation of the dev-orchestration blueprint with `taktusctl run`, prints every run with its ledger and provenance, stops what it started. Needs the repository token, the coding agent's credential and the model endpoint as parameters, each named `TAKTUS_CREDENTIAL_<NAME>_FILE` like every other credential (`CREDENTIALS.md`, the script's header, DEC-0018); `docs/runs/first-run.md` is the record of the first time it ran end to end. **It isolates nothing**: the worker runs by endpoint, as a plain process on the machine with the machine's whole network, so `frame.allowed_hosts` is declared and not enforced — a development shape, said in the script's own header (DEC-0022) |
| `removal_test.sh` | `tools/removal_test.sh [--with-example]` | the removal test for every integration this instance is configured with, in one command: S-01 of the self-operation blueprint once per integration through `taktusctl run`, the verdicts in the ledger as `removal.tested`; `--with-example` starts the reference worker and registers the shipped example first, which is what the weekly job does (`.github/workflows/removal-test.yml`). Exit 0 whatever the verdicts — a verdict is a result; 3 when a run did not finish |
| `generate.py` | `make generate` | writes `api/openapi.yaml` from the FastAPI application (`src/taktus/adapters/driving/rest`), built at the root with the path prefix as a server variable; the file is committed and `tests/adapters/rest/test_openapi.py` fails when it is out of date. The shared kernel is a checked binding, not generated (`docs/architecture/project-structure.md` §4). The same target then writes section 3 of `docs/status.md` through `check_status.py --write` |

`validate_contracts.py` carries its own dependencies in a PEP 723 header, so `uv run
tools/validate_contracts.py` works without the project installed. A third party can check a contract
with nothing but that file. `check_decisions.py`, `check_adrs.py`, `check_status.py` and `checkdocs.py` use the standard
library only and run the same way; CI runs the first four without `make install`.

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

Seven targets are for operating and not gates. `make up` brings the control plane up in two
containers (`deploy/docker/compose.yml`: writes the secret files once, builds the image,
applies the migrations, waits for readiness), `make up-dev` does the same with the reference
worker layered in from its own image (`compose.reference-worker.yml`, development only),
`make down` stops either and keeps every volume, and `make verify-compose` runs
`deploy/docker/verify.sh` — from nothing, through a check that the control plane image holds
no worker code, to a run that survives a killed container. `make db-up` and `make db-down`
start and stop the development database (`deploy/docker/compose.dev.yml`; `db-down` keeps
the volume), and `make migrate` runs the Alembic migrations against
`TAKTUS_DATABASE_URL_FILE` or `TAKTUS_DATABASE_URL`. All seven need `docker` except
`migrate`.

**A gate that cannot run says why.** An unclear message is a defect, not a minor annoyance —
the same rule ADR-0017 applies to decision requests, applied to tooling.
