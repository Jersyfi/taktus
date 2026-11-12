# ADR-0273 — A partner exchange registers only under a data contract its checks hold

**Status:** accepted · extends ADR-0011, ADR-0185, ADR-0233 · UC-15.3 · DEC-0228

## Context

UC-15.3 requires that no data is exchanged with a partner — a supplier, a customer, an authority —
without a documented data contract: the fields, which are mandatory, the frequency, and who is
responsible on each side. A process version that imports from or exports to a partner without
one does not register. The contract is part of the version. Every received message is checked
against it before anything of it is mapped, and every export before it is sent; a deviation is
escalated, never corrected. An open standard is used where one exists, and a proprietary format
says why.

The invoice-to-payment blueprint reads incoming electronic invoices through `documents.invoices`
(ADR-0169), the one partner format a connector of this repository reads. Its steps declared the
shape of what they read (ADR-0233), and no contract.

## Decision

### 1. The contract is a declaration of the version

A bundle's `contracts` maps a name to a data contract: the `partner`, in words; the `direction`,
`import` or `export`; the open `standard` it follows, or, where there is none, `proprietary`
with the reason the partner offers nothing else; the `fields`, each with whether it is
`required`; the `frequency` at which an exchange is expected; who is `responsible` — `ours`, a
role, and `theirs`, in words; and the `steps` that exchange under it. Changing it changes the
version.

### 2. Registration refuses an exchange without one

The process component's rule (`domain/service/partners.py`) refuses a version:

- where a step calls an operation of a capability that carries a partner's data —
  `documents.invoices` — and no contract names it;
- where a contract names a step the version does not have, or one step is named by two;
- where an `import` step does not carry a `source_shape` check whose columns hold every required
  field: the message is checked against the contract before anything of it counts, and a step
  after it reads nothing of a message that fails (ADR-0152);
- where an `export` step does not depend on a step that carries such a check over the document
  it sends;
- where a contract names neither a standard nor the reason for a proprietary format, or both;
- where a contract names a frequency and the version expects no run (ADR-0107), so that a
  missing exchange would not be noticed.

### 3. A deviation is escalated

A message that lacks a required field fails its check: the step fails with `check_failed`
naming the columns it found and those the contract requires, the run escalates to a person
(UC-4.5), and nothing after it maps, completes or guesses the message.

## Alternatives

- **A contract as a document beside the bundle.** It would change without a new version, and
  registration could not hold a step to it.
- **The connector declares which capabilities carry a partner's data.** A change of the connector
  contract for one flag; the process component knows the capabilities by name already.

## Consequences

- `contracts` is a new bundle field and a column of `process_version` (migration `0104`). Both
  B-10.03 bundles declare the supplier-invoice contract of EN 16931, and their read checks the
  mandatory business terms.

## Where this promise ends

- **One partner capability is known.** A partner format read through another capability is held
  to a contract only where a contract names its step.
- **The frequency is held by the expected runs**, not per message: two messages in one slot are
  not found as too frequent.
- **Mapping from sample data in dialogue with a person**, data residency for partner data and
  the record of every send as egress are what the change process, UC-11.1 and ADR-0022 already
  do; this decision adds none of them.
