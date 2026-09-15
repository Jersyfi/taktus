# Tools

Repository tooling. Nothing here is part of the product.

| Tool | Runs as | Does |
|---|---|---|
| `validate_contracts.py` | `make gate-contracts` | every schema under `contracts/` is valid JSON Schema 2020-12, carries the `$id` its path prescribes (ADR-0019) and has resolvable `$ref`s; every `openapi.yaml` is 3.1 with resolvable `$ref`s; every example validates; every must-fail example fails; every conformance check W-01..W-12 has a fixture |
| `check_decisions.py` | `make gate-decisions` | every request under `docs/decisions/open/` has the header and the seven sections, none empty, no placeholder, one recommended option; every record under `docs/decisions/` has an `## Outcome` with a date and an answer and is listed in the index; no number is both open and recorded; with `--pr-body` and `--draft` (CI): every decision the pull request names has its file, every BLOCKING file is named, and a BLOCKING decision keeps the pull request a draft; with `--forbid-open-blocking` (main): no BLOCKING file is open |
| `checkdocs.py` | `make gate-docs` | *(from `0.1.0`)* a contract or behaviour change touches its documentation |
| `generate.py` | `make generate` | *(from `0.1.0`)* the shared kernel and API types from `contracts/` |

`validate_contracts.py` carries its own dependencies in a PEP 723 header, so `uv run
tools/validate_contracts.py` works without the project installed. A third party can check a contract
with nothing but that file. `check_decisions.py` uses the standard library only and runs the same
way; CI runs both without `make install`.
