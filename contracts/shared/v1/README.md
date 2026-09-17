# Shared kernel v1

The concepts every part of Taktus agrees on: the core, the workers, the web app and third-party
adapters. Language-neutral JSON Schema 2020-12 (ADR-0016). The Python types under
`src/taktus/shared/v1/` are a binding of these schemas — one frozen model per file, checked
against the schemas and the examples below by `tests/contract` on every run of `make test`
(`docs/architecture/project-structure.md` §4 says why a checked binding and not generation).

One schema per concept. No product name, no Python assumption, no transport detail.

| Schema | Concept | Enforces |
|---|---|---|
| [`Command.json`](Command.json) | the normalised entry into the one execution path | no command without an identity; the reply goes back to a channel capability |
| [`Plan.json`](Plan.json) | what, with what, by when, at which autonomy level | commissioning is a recorded act: `commissioned` is present exactly when the status says so |
| [`Step.json`](Step.json) | one node of a process graph | method, reason and rejected alternatives on every step; exactness on every result-producing step and never on `wait` or `human` (ADR-0018); a fallback on `llm` and `worker`; a pinned model on `ml` and `neural`; `exact` admits `rule` and `statistics` only |
| [`Method.json`](Method.json) | the eight method kinds | plus the subsets `variable`, `pinned`, `producing`, `nonProducing`, `exactAdmissible` |
| [`ExactnessClass.json`](ExactnessClass.json) | how wrong a result may be | `exact`, `sourced`, `tolerant`, `free`; carried by result-producing steps only |
| [`Capability.json`](Capability.json) | what an adapter can do, by function | lowercase dotted, at least two segments, so that a bare product name never validates; `pattern` adds qualifiers and `*` |
| [`AutonomyLevel.json`](AutonomyLevel.json) | the role a person plays in the loop | 1 to 4 |
| [`Anchor.json`](Anchor.json) | an act that stays with a person | legal or strategic; at least one selector; the decider is a role |
| [`Consumption.json`](Consumption.json) | the raw quantities a step used | at least one quantity; `compute_seconds` never without `resource_class`; money as a map by currency code |
| [`Artifact.json`](Artifact.json) | a result that is data | referenced by `sha256:` digest; the same shape serves as input document |
| [`LedgerEntry.json`](LedgerEntry.json) | one link of the hash chain | references only, no payload; `prev_hash` null only for the first entry |
| [`Provenance.json`](Provenance.json) | what a step result is made of (ADR-0021) | one record per completed step run: process version, method and exactness, model and prompt version, adapter and version, inputs with the moment each was read, outputs, result digest, the ledger entry; references only; exactness present exactly for result-producing methods; each input kind names its own fields |
| [`DecisionRequest.json`](DecisionRequest.json) | the planned question about direction | at least two options with exactly one recommendation; a status beyond `open` requires the raw answer, beyond `answered` the interpretation, `applied` the register entry |

## Conventions

- Every schema carries the `$id` its path prescribes: `https://taktus.eu/contracts/` followed by
  the path under `contracts/`, so `shared/v1/Step.json` is
  `https://taktus.eu/contracts/shared/v1/Step.json` (ADR-0019). The file name is the last segment
  of the `$id`. The schemas reference each other by relative path, which resolves identically
  against the namespace and on disk; `make gate-contracts` checks the `$id`.
- Objects are closed (`additionalProperties: false` or `unevaluatedProperties: false`). A field that
  is not in the schema is a finding, not an extension.
- Identifiers are opaque strings. Timestamps are RFC 3339. Digests are `sha256:` plus 64 hex digits.
- Extension by composition: a schema that another schema extends exposes its properties under
  `$defs` without closure (`Consumption.json#/$defs/quantities`), and the extending schema
  closes the result with `unevaluatedProperties: false`.

## Examples

`examples/<schema>/valid/` holds at least two valid instances per schema, `examples/<schema>/invalid/`
instances that must fail; `<schema>` is the concept in kebab-case (`exactness-class` for
`ExactnessClass.json`). `make gate-contracts` checks both.
