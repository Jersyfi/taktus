# ADR-0220 — What a version means, and how long a deprecated one is served

**Status:** accepted · builds on ADR-0019 (contract identity) and ADR-0171 (a published contract
changes only compatibly) · roadmap `1.0.0`, "versioning and deprecation rules" · anchors M3.5,
M3.6

## Context

The roadmap's condition for `1.0.0` asks for written rules: what a minor and a major change to
the product and to a contract mean, how long a deprecated `v1` is served, and how an
installation learns of it. Parts of the answer exist in three places. ADR-0019 gives every
contract a major version in its `$id`. ADR-0171 says which change of a schema is compatible and
fails a breaking one after the first release. The upgrade guide says how an installation moves
from one version to the next. Nothing says what the product's own version number promises, how
long an old contract major is kept once a new one exists, or how anybody is told that something
will go.

An operator at autonomy level 4 runs a department on Taktus (ADR-0013). A part of the HTTP
surface or a contract that disappears between two upgrades stops that department. The rule
must therefore be checkable before the change ships, not discovered after it.

## Decision

### 1. The product's version is semantic

The product carries one version, `MAJOR.MINOR.PATCH`, the tag of its release (M3.6). Each part
promises something to an installation that upgrades:

| Part | What it may change | What it never changes |
|---|---|---|
| **PATCH** | fixes and documentation | a contract, a route, a setting's meaning, the database schema's direction |
| **MINOR** | new features; a new contract major beside the old one; a new route; a new setting; a migration the guide's downgrade reverses; a deprecation | a published contract, a route or a setting is never removed or changed incompatibly |
| **MAJOR** | the removal of what a minor release deprecated, and only that | nothing is removed that was not deprecated in an earlier release |

A pre-release (`-rc.N`, `-beta.N`) promises nothing of the table. The first release that
promises it is `1.0.0`.

### 2. A contract changes as ADR-0171 says, and an old major stays

A schema changes compatibly within its major, as ADR-0171 classifies it. A breaking change is a
new major under a new `$id`. When `v2` of a contract is released, `v1` becomes **deprecated**.
It is served beside `v2` until the later of two moments: the next product major after the
release that brought `v2`, and twelve months after that release. Both conformance suites go on
holding the reference adapters to `v1` while it is served.

### 3. A deprecation names its removal, where the gate can read it

Whatever is deprecated carries two annotations, side by side:

- `deprecated: true`, the keyword JSON Schema 2020-12 and OpenAPI 3.1 both define;
- `x-taktus-removal`, the product major that removes it, as `N.0.0`.

On an operation of the HTTP surface or of a contract's `openapi.yaml`, a third annotation,
`x-taktus-deprecated`, names the date of the release that deprecated it, as `YYYY-MM-DD`.
`make gate-contracts` fails a schema, a property or an operation under `contracts/` that is
deprecated without a removal of the form `N.0.0`. `tests/adapters/rest/test_versioning.py`
fails the same on `api/openapi.yaml`, and an operation without its date. The classifier of
ADR-0171 treats all three as annotations: a deprecation is compatible, the removal later is not.

### 4. An installation learns of a deprecation in three places

1. **In every answer.** A deprecated operation of the HTTP surface answers with the header
   `Deprecation` of RFC 9745, the date of its deprecation as a structured date
   (`Deprecation: @1767225600`), and with `Taktus-Removal: N.0.0`. A client logs what it is
   still calling.
2. **In the interface description.** `api/openapi.yaml` and every contract's documents mark the
   deprecated parts with their removal, so a generated client marks them too.
3. **In the upgrade guide.** Every release that deprecates something names it in the guide's
   section for that release, with its replacement and its removal version; every major release
   names what it removes.

## Alternatives

- **A calendar alone, without the product major.** A removal on a date would let a minor
  release remove what an installation still calls. The major is what an operator plans an
  upgrade by.
- **Serving an old contract major for as long as anybody uses it.** No installation reports its
  callers to the project, so "as long as anybody uses it" cannot be checked. A stated span can.
- **A custom header alone.** RFC 9745 is the published way to say a resource is deprecated, and
  a client library may already read it. The removal version has no standard header, hence
  `Taktus-Removal` beside it.

## Consequences

- `tools/validate_contracts.py` checks the annotations of §3 on every schema and contract
  OpenAPI document; `tools/contract_compat.py` counts them as annotations.
- The HTTP surface adds the headers of §4.1 to every operation marked deprecated
  (`adapters/driving/rest/deprecation.py`).
- Nothing is deprecated today. The rules apply from the first deprecation on.
- The upgrade guide gains the section that lists deprecations per release.

## Where this promise ends

The gate checks that a deprecation names its removal; it does not check that the removal
happens in that major, nor that anything is removed only after it was deprecated. That stays
with the person who prepares the major release (M3.6), who reads the deprecations the gate
lists. The twelve months of §2 are counted from a release's date, which the repository's tags
carry; no check counts them. The header of §4.1 is set on the HTTP surface only: a worker or a
connector that speaks a deprecated contract major learns of it from the contract's documents
and the guide, not from an answer. The table of §1 promises what a release changes in Taktus,
not in a worker, a connector or a model an operator added, which follow their own versions.
