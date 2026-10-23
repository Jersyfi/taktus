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
| [`Step.json`](Step.json) | one node of a process graph | method, reason and rejected alternatives on every step; exactness on every result-producing step and never on `wait` or `human` (ADR-0018); a fallback on `llm` and `worker`; a pinned model on `ml` and `neural`; `exact` admits `rule` and `statistics` only; `checks` from the catalogue of `Check.json`, never on `wait` or `human`. Added 2026-10-11, optional: every step written before is valid as it is; registration requires a check on an `exact` step (ADR-0082) |
| [`Check.json`](Check.json) | a machine check from the fixed catalogue (UC-4.13) | one row per `kind` — `reconciliation`, `agreement`, `bounds`, `approval`, `sampling`, and `recomputation`, provisional under DEC-0173 — each with exactly the parameters its row needs and none of another row's; a decider is a role, never a person |
| [`Method.json`](Method.json) | the eight method kinds | plus the subsets `variable`, `pinned`, `producing`, `nonProducing`, `exactAdmissible` |
| [`ExactnessClass.json`](ExactnessClass.json) | how wrong a result may be | `exact`, `sourced`, `tolerant`, `free`; carried by result-producing steps only |
| [`Capability.json`](Capability.json) | what an adapter can do, by function | lowercase dotted, at least two segments, so that a bare product name never validates; `pattern` adds qualifiers and `*` |
| [`AutonomyLevel.json`](AutonomyLevel.json) | the role a person plays in the loop | 1 to 4 |
| [`Anchor.json`](Anchor.json) | an act that stays with a person | legal, strategic or correction (ADR-0022); at least one selector; the decider is a role |
| [`Consumption.json`](Consumption.json) | the raw quantities a step used | at least one quantity; `compute_seconds` never without `resource_class`; money as a map by currency code |
| [`Artifact.json`](Artifact.json) | a result that is data | referenced by `sha256:` digest; the same shape serves as input document |
| [`Autonomy.json`](Autonomy.json) | a process's autonomy with its reason (ADR-0026) | `level`, `reason`, and `toward_next` — required below level 4, absent at 4; `actions` sets a level per tool action, each with the same three fields and never above the process's, and the lowest that applies to a step holds; `history` is the number of clean runs in a row a raise needs (ADR-0039). The two were added 2026-10-09, optional: every statement written before is valid as it is |
| [`LedgerEntry.json`](LedgerEntry.json) | one link of the hash chain | references only, no payload; `prev_hash` null only for the first entry; `egress.*` kinds record what left the system (ADR-0022); `removal.tested` records a removal test's verdict — `broke`, `changed`, `untested` or `exception` — for the adapter it names, with the result's digest; `capacity.memory` and `capacity.storage.<place>` record a platform resource crossing into *act* or back to *ok* (docs/architecture/platform.md); `refs.trace_id` names the trace the entry was recorded in, so that an entry and a trace can be joined; `rehearsal: true` marks every entry of a rehearsal run — no outward operation acted, a rehearsed outward step finishes with outcome `rehearsed`, and no egress entry is written (ADR-0030). Added 2026-09-30, optional: every entry written before carries no such field, and its hash is unchanged. `step.awaiting`, `step.confirmed`, `step.performed` and `run.waiting_human` record a step that waits for a person and the person's answer, with the person in `refs.actor`; `autonomy.raised`, `autonomy.refused` and `autonomy.proposed` record a raise of an autonomy level, its refusal with what was missing as outcome, and Taktus's proposal (ADR-0039); `process.refused` with outcome `administers` records a version not registered because a step names a credential that administers the instance's own platform, or one declared about nothing (ADR-0052); `process.deactivated` records a process switched off, with the version that was active in `refs.process_version` and who switched it off in `refs.actor` (ADR-0066); `process.commissioned` records a person's proposal registered, with the version in `refs.process_version`, who commissioned it in `refs.actor` and the proposal as outcome, and `process.rolled_back` an earlier version registered again, outcome `restored` (ADR-0091); `refs.report_id` names a report to the owner, the record a `report.*` entry points to and its renderings are composed from (ADR-0045) — added 2026-10-09, optional, so every entry written before is unchanged; `run.ended` records how a run ended — `ok`, `empty` or `error` — with `duration_seconds`, `trigger.empty` a schedule trigger whose `each` list was empty, `incident.raised`, `incident.recorded` and `incident.closed` an incident named in `refs.incident_id`, and `watch.empty_share` a process whose share of empty ends crossed the tenant's threshold or fell back, and `watch.configured` the tenant's watch configuration set (ADR-0107) — added 2026-10-18, optional, so every entry written before is unchanged; `corridor.changed` records a new version of a signal's corridor with the person in `refs.actor` and the version's digest, `corridor.refused` a change refused with its reason as outcome, and `incident.raised` or `incident.recorded` with outcome `red` a signal's red value (ADR-0109); `proposal.decided` records a person's decision on a step proposed at level 1 or 2 — `released`, `corrected` or `rejected` — with `refs.action`, the tool action whose level held the step, and no actor; `autonomy.lowered` a level lowered by rule, with the new level as outcome, and `run.lowered` a run that took it on at a step boundary; `corrections.configured` a tenant's correction limits set (ADR-0110) — added 2026-10-18, optional, so every entry written before is unchanged; `residency.configured` a tenant's residency rule set, with the location it permits as outcome (ADR-0116); `frame.refused` a connector call a step's frame refused, or a connector refused as outside the case's scope, with the reason as outcome, and `sources.configured` a tenant's declaration of its sources changed (ADR-0130) |
| [`Provenance.json`](Provenance.json) | what a step result is made of (ADR-0021) | one record per completed step run: process version, method and exactness, model and prompt version, adapter and version, the route of a step on a model through its purpose's chain (ADR-0116), the scope of a step that served a case — its subject's identifier (ADR-0130), inputs with the moment each was read, outputs, result digest, the ledger entry; references only; exactness present exactly for result-producing methods; each input kind names its own fields |
| [`DecisionRequest.json`](DecisionRequest.json) | the planned question about direction | at least two options with exactly one recommendation, which carries its reason; a status beyond `open` requires the raw answer, beyond `answered` the interpretation, `applied` the register entry |

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
