# Tools

Repository tooling. Nothing here is part of the product.

| Tool | Runs as | Does |
|---|---|---|
| `validate_contracts.py` | `make gate-contracts` | every schema under `contracts/` is valid JSON Schema 2020-12, carries the `$id` its path prescribes (ADR-0019) and has resolvable `$ref`s; every `openapi.yaml` is 3.1 with resolvable `$ref`s; every example validates; every must-fail example fails; every conformance check W-01..W-12 has a fixture |
| `check_decisions.py` | `make gate-decisions` | every request under `docs/decisions/open/` has the header and the seven sections, none empty, no placeholder, one recommended option; every record under `docs/decisions/` has an `## Outcome` with a date and an answer and is listed in the index; no number is both open and recorded; with `--pr-body` and `--draft` (CI): every decision the pull request names has its file, every BLOCKING file is named, and a BLOCKING decision keeps the pull request a draft; with `--forbid-open-blocking` (main): no BLOCKING file is open |
| `checkdocs.py` | `make gate-docs` | a change to a contract, a tool, a make target, the architecture contracts, a component, a port, an adapter, a worker, a blueprint or a deployment touches the documentation of that place in the same change; compares with `origin/main` (or `BASE=<ref>`); nothing changed, or nothing that a rule covers, is green |
| `gate.py` | `make test`, `make gate-arch`, `-conformance`, `-governance`, `-exactness` | runs pytest on one directory; "no tests collected" reports "no targets yet" and green, every other exit code passes through |
| `generate.py` | `make generate` | *(from `0.1.0`)* the shared kernel and API types from `contracts/` |

`validate_contracts.py` carries its own dependencies in a PEP 723 header, so `uv run
tools/validate_contracts.py` works without the project installed. A third party can check a contract
with nothing but that file. `check_decisions.py` and `checkdocs.py` use the standard library only
and run the same way; CI runs the first two without `make install`.

**A gate with nothing to check reports green and says so.** A gate that is red because it found
nothing is broken, not strict. `make gates` needs `uv` and `gitleaks` on the path, and nothing else
— no Node, no database.
