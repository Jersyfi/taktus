# DEC-0001 — Contract identity

**Category:** NON-BLOCKING
**Raised in:** [#1](https://github.com/Jersyfi/taktus/pull/1), as open point 1 of its description
**Issue:** none; raised before ADR-0017, in the description only
**Provisional answer:** no identifier; the schemas referenced each other by relative file path, which works from disk and is changed by one additive edit

## 1. What this is about

Taktus talks to the programs it conducts — coding agents, script runners, training jobs, chat
tools — through *contracts*: machine-readable descriptions of what the two sides send each other.
They live under `contracts/` in this repository, written as JSON Schema, a standard format for
describing the shape of data.

A JSON Schema may carry an identifier: a web address that names it. The address does not have to
be reachable; it is a name. But it has to be under a domain, and a domain belongs to somebody.
The first pull request that wrote the contracts left the identifier out, because it did not want
to put a domain the project might not own into every public file. The question was which domain,
and in what form, the contracts should be named under.

## 2. Why you are being asked

`anchors.md` §1, row O7: *anything published under the project's name — the contract namespace.*
The identifier is the public name of the contract. It appears in every copy of every schema, and
anyone who implements a Taktus contract will quote it.

## 3. What you must decide

Under which web address are the contracts named?

## 4. What you need to know to decide

- **Identifier (`$id`).** A field in a JSON Schema holding an absolute web address. Tools use it
  for two things: to tell two schemas apart, and as the base against which a schema's references
  to other schemas are resolved. A schema without one is identified by its file path only.
- **Namespace.** The common prefix of all identifiers, for example
  `https://taktus.eu/contracts/`. Everything after it names one schema.
- **Serving.** Making the address actually answer with the schema. Not required for validity; a
  name that does not resolve is still a valid name, and every tool in use loads the schemas from
  the repository. Serving is useful later, when third parties implement the contracts.
- **What exists today.** Thirteen schemas in two families, `shared` and `worker`, referencing each
  other by relative path. Three more families are planned: `connector`, `model`, `process`, and
  one for `events`.
- **What the decision commits the project to.** The domain must stay with the project for as long
  as any version of the contracts is in use: a contract whose name changes is a different
  contract. Once the addresses are served, they must serve the same bytes for as long as that
  version is current — a released version of a schema is never changed in place, a change becomes
  the next version. Serving them is a later task and does not have to happen before `1.0.0`.
- **Principle 13** of the project (CLAUDE.md §5): freedom instead of vendor lock-in. The name of a
  contract is the most visible place where that principle either holds or does not.

## 5. Options

### Option A — the project's own domain, `https://taktus.eu/contracts/<family>/v1/<Concept>.json` (recommended)

- **Meaning:** every schema is named by the project's domain followed by its path in the
  repository. `contracts/shared/v1/Step.json` is `https://taktus.eu/contracts/shared/v1/Step.json`.
- **Consequence:** the identity of the contracts belongs to the project, not to a hosting
  provider. Serving them later is a static copy of the directory. The schema files are named after
  their concept (`Step.json`) so that file path and address agree.
- **Effort:** one change to every schema and the validator, about two hours; registering nothing,
  the domain is already held.
- **Reversibility:** cheap until the first release; after it, a change of namespace is a new
  contract version.
- **Why recommended:** it is the only option under which the name of the contract says nothing
  about where the repository happens to be hosted.

### Option B — GitHub raw URLs, `https://raw.githubusercontent.com/Jersyfi/taktus/main/contracts/...`

- **Meaning:** the address at which GitHub serves the file from the repository.
- **Consequence:** the addresses resolve immediately, nothing to serve. But the name of every
  contract now contains the hosting provider and the account name. Moving the repository, or the
  provider changing its URL scheme, renames every contract. This contradicts principle 13 at its
  most visible point.
- **Effort:** the same change to every schema; nothing to serve.
- **Reversibility:** the same as A until the first release; after it, the same cost — but the
  reason to change would arrive from outside, at a time not of the project's choosing.

### Option C — a separate subdomain, `https://schemas.taktus.eu/...`

- **Meaning:** like A, under a dedicated host name.
- **Consequence:** one more certificate and one more thing to operate, for no gain: a path under
  the main domain is as stable and shorter.
- **Effort:** as A, plus the subdomain.
- **Reversibility:** as A.

## 6. What is blocked

Nothing was blocked; the schemas worked without an identifier. #1 gave no date, which was a
defect of the request: it should have said before `0.1.0`. Without an answer before `0.1.0`,
the first release would have shipped contracts with no public name, and every third party would
have invented its own — which is what makes the answer needed before the release, not before the
merge.

## 7. How to answer

"DEC-0001: Option A", "DEC-0001: Option B" or "DEC-0001: Option C". A different domain: "DEC-0001:
Option A under another domain", naming it — read back and confirmed before it is applied.

## Outcome

**Decided:** 2026-09-15
**Answer:** Option A. The namespace is `https://taktus.eu/contracts/<family>/v1/<Concept>.json`.
**Reasoning given:** the owner holds `taktus.eu`. GitHub raw URLs were rejected because they would
tie the identity of the contracts to one hosting provider, contradicting principle 13 where it is
most visible. A separate subdomain was rejected because it adds a certificate and an operational
concern without a gain. An identifier that does not yet resolve is valid and breaks nothing;
serving the contracts is a later task.
**Recorded in:** [ADR-0019](../adr/ADR-0019-contract-identity.md), applied in
[#3](https://github.com/Jersyfi/taktus/pull/3)
