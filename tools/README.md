# Tools

Repository tooling. Nothing here is part of the product.

| Tool | Runs as | Does |
|---|---|---|
| `validate_contracts.py` | `make gate-contracts` | every `*.schema.json` under `contracts/` is valid JSON Schema 2020-12 with resolvable `$ref`s; every `openapi.yaml` is 3.1 with resolvable `$ref`s; every example validates; every must-fail example fails; every conformance check W-01..W-12 has a fixture |
| `checkdocs.py` | `make gate-docs` | *(from `0.1.0`)* a contract or behaviour change touches its documentation |
| `generate.py` | `make generate` | *(from `0.1.0`)* the shared kernel and API types from `contracts/` |

`validate_contracts.py` carries its own dependencies in a PEP 723 header, so `uv run
tools/validate_contracts.py` works without the project installed. A third party can check a contract
with nothing but that file.
