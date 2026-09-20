# ADR-0019 — Contract identity

**Status:** accepted · decided by the owner, recorded as DEC-0001

## Context
The contracts under `contracts/` are JSON Schema documents. A JSON Schema may carry an `$id`: an
absolute URL that names the schema and serves as the base against which its relative references
are resolved. Until now the schemas carried none, because an `$id` needs a namespace — a domain —
and pull request #1 did not want to write a domain the project might not own into every public
schema. Without an `$id` the schemas resolve from disk only, and two copies of a schema cannot be
told apart by anything but their bytes.

The owner holds the domain `taktus.eu` and has decided to use it.

## Decision
Every schema carries an `$id` of the shape

```
https://taktus.eu/contracts/<family>/v1/<Concept>.json
```

with `<family>` one of `shared`, `worker`, `connector`, `model`, `process`, `events`, and
`<Concept>` the concept's name in PascalCase — the same word as the schema's `title`.

Three rules follow from the shape:

1. **The `$id` is the repository path.** The `$id` of a schema is `https://taktus.eu/contracts/`
   followed by the schema's path under `contracts/`. The file is therefore named after the
   concept, `Step.json`, not `step.schema.json`. Relative references (`Method.json`,
   `../../shared/v1/Capability.json`) resolve identically against the namespace and on disk, and
   serving the contracts later is a static copy of the directory. `make gate-contracts` checks
   that every `$id` matches its path.
2. **A released v1 schema is immutable.** Once a version of Taktus that uses a schema is released,
   the bytes behind its `$id` do not change. A change becomes `v2` under a new `$id`. Until the
   first release, v1 may still move.
3. **The URLs serve the same bytes for as long as v1 is current.** This is what the decision
   commits the project to: the domain stays with the project, and once the contracts are served,
   they are served unchanged until v1 is retired. Serving them is a later task. An `$id` that does
   not yet resolve is valid and breaks nothing, because every reference still resolves locally and
   every validator in use loads the schemas from the repository.

The same rule names every other file under `contracts/`, such as `openapi.yaml`, even where the
format has no `$id` field: its URL is its path.

## Alternatives
- **GitHub raw URLs** (`https://raw.githubusercontent.com/...`). They would have tied the identity
  of the contracts to one hosting provider — a contradiction of principle 13, freedom instead of
  vendor lock-in, at its most visible point: the name of the contract itself. Moving the
  repository would have changed the identity of every schema.
- **A separate subdomain** (`schemas.taktus.eu`). It adds a certificate and an operational concern
  and gains nothing: the path under the main domain is just as stable and shorter.
- **No `$id`, references by relative path only** (the state after #1). Works from disk, but a
  schema without an `$id` has no identity that survives copying, and every consumer invents its
  own base URI. Acceptable as an interim state, not as the contract.

## Consequences
- The schema files are renamed to `<Concept>.json`; the examples directories keep their
  kebab-case names (`exactness-class/` for `ExactnessClass.json`).
- `tools/validate_contracts.py` registers every schema under its `$id` and fails on an `$id` that
  does not match the path.
- Serving `https://taktus.eu/contracts/` is a task for the release that first ships a contract,
  no later than `1.0.0`, when the contracts are frozen (roadmap).
- The namespace is public communication under the project's name (anchors.taktus.md, M3.7). Changing
  it is the owner's call.
