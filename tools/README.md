# Tools

Repository tooling. Nothing here is part of the product.

| Tool | Runs as | Does |
|---|---|---|
| `validate_contracts.py` | `make gate-contracts` | every schema under `contracts/` is valid JSON Schema 2020-12, carries the `$id` its path prescribes (ADR-0019) and has resolvable `$ref`s; every `openapi.yaml` is 3.1 with resolvable `$ref`s; every example validates; every must-fail example fails by schema — except transcripts, which must be schema-valid and whose stream rule `tests/conformance` checks; every conformance check W-01..W-12 has a fixture |
| `check_decisions.py` | `make gate-decisions` | every request under `docs/decisions/open/` has the header and the seven sections, none empty, no placeholder, one recommended option; every record under `docs/decisions/` has an `## Outcome` with a date and an answer and is listed in the index; no number is both open and recorded; with `--pr-body` and `--draft` (CI): every decision the pull request names has its file, every BLOCKING file is named, and a BLOCKING decision keeps the pull request a draft; with `--forbid-open-blocking` (main): no BLOCKING file is open |
| `checkdocs.py` | `make gate-docs` | a change to a contract, a tool, a make target, the architecture contracts, a component, a port, an adapter, the composition root, a wire format, a worker, a blueprint, an example or a deployment touches the documentation of that place in the same change; compares with `origin/main` (or `BASE=<ref>`); nothing changed, or nothing that a rule covers, is green |
| `gate.py` | `make test`, `make gate-arch`, `-conformance`, `-governance`, `-exactness` | runs pytest on one directory; "no tests collected" reports "no targets yet" and green, every other exit code passes through |
| `preflight.sh` | every make target, through `need-<tool>`; `make doctor` | a missing tool names itself, what it is for and the one command that installs it, instead of `make: uv: No such file or directory`; `make doctor` reports two levels — the system tools, and the project environment with the tools the gates actually invoke through `uv run` (ruff, mypy, pytest, lint-imports, taktusctl) — says which is incomplete, and exits non-zero if either is |
| `generate.py` | `make generate` | says what is generated from `contracts/` — nothing yet: the shared kernel is a checked binding (`docs/architecture/project-structure.md` §4), `api/openapi.yaml` arrives with the REST interface |

`validate_contracts.py` carries its own dependencies in a PEP 723 header, so `uv run
tools/validate_contracts.py` works without the project installed. A third party can check a contract
with nothing but that file. `check_decisions.py` and `checkdocs.py` use the standard library only
and run the same way; CI runs the first two without `make install`.

**A gate with nothing to check reports green and says so.** A gate that is red because it found
nothing is broken, not strict. `make gates` needs `uv` and `gitleaks` on the path, and nothing else
— no Node, no database, and no `make install` first. Every target that runs a tool from the
project environment depends on `env`, which syncs the environment once when `pyproject.toml` or
`uv.lock` is newer than its stamp (`.venv/.synced`) or the environment is absent; a fresh clone
is green in one command. `make doctor` says which of the two levels is present; Node is listed
as optional, for the web targets that will need it. CI reaches the same preflight through
`need-<tool>` on every target it runs, so it does not call `make doctor` (its secret scan runs
through an action that brings its own `gitleaks`).

**A gate that cannot run says why.** An unclear message is a defect, not a minor annoyance —
the same rule ADR-0017 applies to decision requests, applied to tooling.
