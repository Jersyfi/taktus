# DEC-0231 — When the v1 contracts freeze

**Category:** NON-BLOCKING
**Raised in:** the pull request of release 1.0 (DEC-0228), area platform
**Issue:** [#677](https://github.com/Jersyfi/taktus/issues/677)
**Needed by:** 2026-12-01
**Provisional answer:** nothing is frozen; `contracts/FREEZE.json` does not exist, and the v1 contracts go on changing only compatibly (ADR-0171) until the owner answers.

## 1. What this is about

Taktus talks to everything outside it — the programs that carry out work, the connections to
other systems, the language models — through written agreements called **contracts**. Each
contract says exactly which messages may be sent and what each field means. Whoever builds an
adapter, inside the project or outside it, builds against these contracts.

Today the contracts are at their first version, `v1`. Since the first release they may change
only in ways that break nobody: a field may be added, never removed. Version 1.0.0 of Taktus asks
for more: the contracts **freeze**. From the freeze on, a `v1` contract does not change at all,
not even by adding a field. Anything new goes into a `v2` beside it.

The repository already has the machinery. A record, `contracts/FREEZE.json`, would name every
file of a frozen contract with a fingerprint of its exact bytes and the date. The check that runs
on every change then fails any change to a frozen file, and any file added to a frozen version.
The record does not exist. Writing it is the freeze.

## 2. Why you are being asked

Entry M3.5 of `docs/decisions/anchors.taktus.md`: "Anything that would break a published
contract." Freezing does not break a contract, but it decides that no further change of `v1` is
possible, which is the same commitment seen from the other side; the roadmap says it in so many
words: "Freezing is proposed as a decision request (M3.5) with the evidence that no open use case
needs a change." Entry M3.6, preparing a release, is the owner's too, and the freeze holds through
the stabilisation phase before the tag.

**Sources checked:** `docs/vision/` (principle 13, freedom instead of lock-in, asks for stable interfaces but sets no date); `docs/roadmap.md`, *The road to 1.0.0* (freezing is a milestone with its own
check, proposed as a decision request); ADR-0019 (contract identity, a breaking change is a new
major), ADR-0171 (a published contract changes only compatibly, the freeze record's shape),
ADR-0220 (deprecation of an old major); both anchor pages (M3.5, M3.6 make it the owner's; no
mode-1 or mode-2 entry covers a freeze); the register (no decision on the freeze date; DEC-0222
puts the beta before 1.0.0). None of them sets the date, nor says whether every family freezes at
once.

## 3. What you must decide

When do the v1 contracts freeze, and do all of them freeze together?

## 4. What you need to know to decide

- **What would be frozen.** Twenty-two files in eight families, every schema and interface
  description under `contracts/<family>/v1/`: the worker contract (`Worker.json`,
  `openapi.yaml`), the connector contract (`Connector.json`), the model contract (`Model.json`),
  the events (`Event.json`), the catalogue (`Catalogue.json`), the changes (`Changes.json`), and
  the shared kernel of fifteen schemas (`Anchor`, `Artifact`, `Autonomy`, `AutonomyLevel`,
  `Capability`, `Check`, `Command`, `Consumption`, `DecisionRequest`, `ExactnessClass`,
  `LedgerEntry`, `Method`, `Plan`, `Provenance`, `Step`). The family `process` holds only a README
  and has nothing to freeze. READMEs, examples and conformance texts are not frozen.
- **What the record looks like.** `{"frozen": "YYYY-MM-DD", "decision": "DEC-0231", "files":
  {"worker/v1/Worker.json": "sha256:" followed by the file's fingerprint, and one line per file}}`. The fingerprints are computed from the files on
  `main` on the day of the freeze, by `sha256sum`, not by hand.
- **The evidence the roadmap asks for.** Seventeen use cases that mention a contract are still
  `specified` or `building`: UC-1.1, UC-1.3, UC-4.10, UC-5.2, UC-5.3, UC-5.8, UC-6.8, UC-6.11,
  UC-7.3, UC-8.1, UC-8.3, UC-8.8, UC-12.1, UC-14.1, UC-14.4, UC-15.3, UC-15.5. Before the freeze,
  each must be read against the contracts it rests on and either shown to need no change of `v1`,
  or its change made first. That reading is not done here; it is the first step of every option
  below that freezes.
- **What a freeze commits the project to.** After it, a new field any adapter needs is a `v2` of
  that contract, served beside `v1` for at least twelve months and until the next major release
  (ADR-0220). That costs a second schema, a second conformance suite run and an adapter that
  speaks both, for every such change.
- **What not freezing costs.** Version 1.0.0 cannot be tagged: the roadmap names the freeze as
  its condition. Outside authors of adapters build against a contract that can still grow.

## 5. Options

### Option A — Freeze every family together, once the beta's findings are in (recommended)

- **Meaning:** after `1.0.0-beta` runs at the business and its findings in the stabilisation
  phase are answered, a session reads the seventeen use cases against the contracts, makes any
  compatible change still needed, computes the fingerprints and writes `contracts/FREEZE.json`
  naming this decision, in a pull request of its own.
- **Consequence:** one date for every contract; the stabilisation phase runs on frozen
  contracts; a finding of the beta that needs a field still gets it before the freeze.
- **Effort:** half a day of a session for the reading and the record.
- **Reversibility:** costly: undoing a freeze after outside adapters were built against it
  breaks the promise it made; before anyone builds on it, cheap.
- **Why recommended:** the beta is the first time a business runs Taktus; freezing before its
  findings would turn any field it needs into a `v2`.

### Option B — Freeze now, on the state of the release 1.0 pull request

- **Meaning:** the fingerprints of the twenty-two files on `main` after release 1.0 lands go
  into the record at once.
- **Consequence:** the stabilisation phase starts sooner; every field the beta shows to be
  missing becomes a `v2`.
- **Effort:** an hour, plus the reading of the seventeen use cases.
- **Reversibility:** as A, but the chance of needing a `v2` soon is higher.

### Option C — Freeze family by family, the worker and connector contracts first

- **Meaning:** the two contracts outside authors build against most freeze after the beta; the
  others when their open use cases are built.
- **Consequence:** more than one freeze date; the record names each version as it freezes.
- **Effort:** a session per freeze.
- **Reversibility:** as A, per family.

## 6. What is blocked

Nothing until the stabilisation phase. Tagging `1.0.0` waits for the freeze. If no answer arrives
by 2026-12-01, the provisional answer stands: nothing frozen, every `v1` contract changes only
compatibly, and the tag cannot be cut.

## 7. How to answer

- "DEC-0231: Option A."
- "DEC-0231: Option B."
- "DEC-0231: Option C."
