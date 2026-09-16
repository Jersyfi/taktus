# Shared kernel binding

`v1/` binds `contracts/shared/v1` to Python: one frozen, closed Pydantic model per schema, in a
module named after the schema file (`Step.json` → `step.py`, `LedgerEntry.json` →
`ledger_entry.py`). Hand-written, machine-checked: `tests/contract` fails on any difference to the
schemas and runs every example of the contract through the models. Why a checked binding rather
than generation: `docs/architecture/project-structure.md` §4.

Nothing here imports a component, a port or a technology. Every type has `document()`: the
instance as the JSON document the schema describes.
