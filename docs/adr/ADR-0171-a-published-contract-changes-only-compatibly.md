# ADR-0171 — A published contract changes only compatibly, and a lane classifies every change

**Status:** accepted · amends ADR-0019 rule 2 (a released `v1` schema is immutable) · extends
ADR-0096 §6 phase 4 (a contract-compatibility lane before the contracts freeze) · roadmap
`1.0.0`, "a lane that fails a breaking change of a published contract" (#396); anchor M3.5

## Context

The contracts under `contracts/` are what an adapter's author builds against. A contract is
*published* once a version of Taktus that uses it is released (anchors M3.5, ADR-0019). Changing
a published contract in a way that breaks its consumers is the owner's decision (M3.5). Nothing
noticed such a change until now: `make gate-contracts` checks that a schema is valid and that
its examples hold, not what it was at the last release.

ADR-0019 rule 2 said that the bytes of a released `v1` schema never change. The roadmap says
otherwise: `v1` stops moving at the freeze, a deliberate act of the owner (M3.5), recorded under
`contracts/` with the digest of every schema. Issue #396 asks for a lane before the freeze that
fails a change which breaks a consumer, and so admits one which does not. The two texts
disagree for the time between the first release and the freeze.

## Decision

### 1. Between a release and the freeze, a published schema changes only compatibly

A change is **compatible** when everything the old schema accepted is still accepted and
nothing a reader could rely on is gone. Every other change is **breaking**. Seen from the
consumer — an adapter that sends documents the contract describes, or reads them:

| Breaking | Compatible |
|---|---|
| a property, a definition or a whole schema removed | a property, a definition or a schema added, not required |
| a property newly required, or no longer required | a type or an enum widened |
| a type or an enum narrowed or changed; a `const` added or changed | a bound loosened or removed |
| a bound (`minimum`, `maxLength`, …) added or tightened; a `pattern` or `format` added or changed | a description, title or example changed |
| a changed `$id`, `$schema` or `$ref`; a changed condition (`if`, `not`) | an alternative added to `anyOf` or `oneOf`; a subschema removed from `allOf` |
| additional properties no longer admitted; a subschema added to `allOf` | additional properties now admitted |
| every keyword the classifier does not know | |

A property no longer required counts as breaking: a reader built against the old schema relied
on finding it. A widened enum counts as compatible, as issue #396 has it: every document valid before is
still valid. A new enum value is how the contracts have grown, for example a new event type of
the worker contract. In a contract's `openapi.yaml`, a path, an operation or a component added is
compatible and one removed breaking; a component schema is compared as above. Any other change
to an operation, a server or the version is breaking. The classifier does not judge these, and a
person compares them.

A breaking change is made as a **new major version under a new `$id`**:
`contracts/<family>/v2/<Concept>.json` beside `v1`, which stays as it was. A `v1` schema may be
retired once its successor at a higher major exists. Nothing else makes a breaking change pass.

This amends ADR-0019 rule 2. Its first sentence now reads: *once a version of Taktus that uses
a schema is released, the schema changes only compatibly, and from the freeze not at all.*

### 2. The baseline is the last release

The baseline is the highest tag `vMAJOR.MINOR.PATCH` with no pre-release part that is an
ancestor of the commit checked. A release candidate (`v0.2.0-rc.34`) and a beta are not
releases (NTC-0255). Every schema at the baseline is compared with the schema at the same path
now. With no release yet, nothing is published and `v1` may still move. The check then says so
and classifies the change against the pull request's base, for the reviewer's information, and
passes. A shallow clone has no tags. The check refuses it and does not read it as "no release".

### 3. The lane

`tools/contract_compat.py` is the classifier, as `make gate-compat`. It needs `git` and the
dependencies in its own header, nothing of the project. It runs in CI's lane `contracts`, which
a change under `contracts/` selects (ADR-0096 §3), beside `make gate-contracts`, and on every
push to `main`. `tests/tools/test_contract_compat.py` shows both outcomes against a repository
with a release tag: a compatible change passes; a breaking one fails; the same break passes as
`v2`.

### 4. A freeze record, if one exists, holds every byte

The freeze is the owner's act (M3.5). No session writes its record. If `contracts/FREEZE.json`
exists, `make gate-contracts` holds every file it names to its digest. It also fails any schema
added to a frozen version. A compatible change of a frozen schema fails too. The record's shape
is `{"frozen": "<date>", "decision": "DEC-NNNN", "files": {"<family>/v<N>/<file>":
"sha256:<hex>"}}`.

## Alternatives

- **Every byte immutable from the first release (ADR-0019 rule 2 as written).** Rejected for
  the time before the freeze: it would turn every added optional field into a `v2`. The
  roadmap expects `v1` to keep moving until the freeze. M3.5 keeps only a *breaking* change
  with the owner.
- **A recorded baseline file instead of the release tag.** Rejected: it is one more file that
  every release must rewrite, and the tag already names what was released.
- **A release candidate as the baseline.** Rejected: a candidate is installed only on the
  project's own instance (M1.25), and no adapter author outside the project built against one.
- **A JSON Schema library's own diff.** None in use answers the consumer's question.
  Comparing keyword by keyword with the standard library keeps the check runnable by a third
  party.

## Consequences

- `make gate-compat` joins the lane `contracts` and `make gates`. CI's job `contracts` fetches
  the whole history.
- Before `v0.2.0` or any other release, the lane reports and never fails. It begins to fail
  breaking changes on the first commit after the first release tag.
- A keyword the classifier does not know fails a change that uses it. It does so until the
  classifier is taught the keyword, so an unknown construct never passes unseen.
- `docs/architecture/contracts.md` §8 states the rule for an adapter's author.

## Where this promise ends

The classifier compares schemas structurally, keyword by keyword. It does not decide whether
two differently written schemas accept the same documents. A schema rewritten in an equivalent
form is reported as breaking, and a person then judges it. It follows `$ref` by name, not into
its target: a referenced schema is compared in its own file, and a change there is reported
there, not at every place that refers to it. Alternatives of `anyOf` and `oneOf` are matched
when unchanged and otherwise by position. An added `oneOf` alternative is counted as
compatible even where it overlaps an existing one, which could make a document match twice.
A reader that handles only the enum values it knew may meet a new one. The
classifier calls that compatible, and the contract's README announces the value. The baseline
is a release tag the repository carries. A release published from a commit the
checked one does not descend from is not seen. The check holds the schemas and the contracts'
OpenAPI documents, not their READMEs or conformance texts, and not the HTTP API's
`api/openapi.yaml`.
