# Shared kernel v1

The concepts every part of Taktus agrees on: the core, the workers, the web app and third-party
adapters. Language-neutral JSON Schema 2020-12 (ADR-0016). The Python types under
`src/taktus/shared/` are generated from here by `make generate` and never edited by hand.

One schema per concept. No product name, no Python assumption, no transport detail.

| Schema | Concept | Enforces |
|---|---|---|
| [`command.schema.json`](command.schema.json) | the normalised entry into the one execution path | no command without an identity; the reply goes back to a channel capability |
| [`plan.schema.json`](plan.schema.json) | what, with what, by when, at which autonomy level | commissioning is a recorded act: `commissioned` is present exactly when the status says so |
| [`step.schema.json`](step.schema.json) | one node of a process graph | method, reason and rejected alternatives on every step; exactness on every result-producing step and never on `wait` or `human` (ADR-0018); a fallback on `llm` and `worker`; a pinned model on `ml` and `neural`; `exact` admits `rule` and `statistics` only |
| [`method.schema.json`](method.schema.json) | the eight method kinds | plus the subsets `variable`, `pinned`, `producing`, `nonProducing`, `exactAdmissible` |
| [`exactness-class.schema.json`](exactness-class.schema.json) | how wrong a result may be | `exact`, `sourced`, `tolerant`, `free`; carried by result-producing steps only |
| [`capability.schema.json`](capability.schema.json) | what an adapter can do, by function | lowercase dotted, at least two segments, so that a bare product name never validates; `pattern` adds qualifiers and `*` |
| [`autonomy-level.schema.json`](autonomy-level.schema.json) | the role a person plays in the loop | 1 to 4 |
| [`anchor.schema.json`](anchor.schema.json) | an act that stays with a person | legal or strategic; at least one selector; the decider is a role |
| [`consumption.schema.json`](consumption.schema.json) | the raw quantities a step used | at least one quantity; `compute_seconds` never without `resource_class`; money as a map by currency code |
| [`artifact.schema.json`](artifact.schema.json) | a result that is data | referenced by `sha256:` digest; the same shape serves as input document |
| [`ledger-entry.schema.json`](ledger-entry.schema.json) | one link of the hash chain | references only, no payload; `prev_hash` null only for the first entry |
| [`decision-request.schema.json`](decision-request.schema.json) | the planned question about direction | at least two options with exactly one recommendation; a status beyond `open` requires the raw answer, beyond `answered` the interpretation, `applied` the register entry |

## Conventions

- No `$id` yet. The schemas reference each other by relative path, so they resolve from disk in any
  tool. A namespace is added once the project's domain is settled; it is an additive change.
- Objects are closed (`additionalProperties: false` or `unevaluatedProperties: false`). A field that
  is not in the schema is a finding, not an extension.
- Identifiers are opaque strings. Timestamps are RFC 3339. Digests are `sha256:` plus 64 hex digits.
- Extension by composition: a schema that another schema extends exposes its properties under
  `$defs` without closure (`consumption.schema.json#/$defs/quantities`), and the extending schema
  closes the result with `unevaluatedProperties: false`.

## Examples

`examples/<schema>/valid/` holds at least two valid instances per schema, `examples/<schema>/invalid/`
instances that must fail. `make gate-contracts` checks both.
