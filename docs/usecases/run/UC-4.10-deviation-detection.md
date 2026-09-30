---
id: UC-4.10
title: Deviation detection
component: run
epic: E4
serves: [P8, P10, P12]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0018: 17c99e0eaa3c, ADR-0021: 202e0442e7ec, ADR-0022: 69572977f46b, ADR-0023: 949c6f4e13af, ADR-0024: ac6a1fe1610a}
supersedes: null
---

# UC-4.10 — Deviation detection

## 1. What must be achieved

A run that completes and reports success may still be wrong. A partner changes a field, the
mapping still matches, every run reports success — and for three weeks the data is wrong. There
is no failed run to find, because the fault is in the **result**, not in the execution. This is
a *result defect* (ADR-0021).

Taktus must notice this class of fault. After every completed step that produces a result, and
after every completed run, it checks the result against the properties it is expected to have —
not the run against success.

The expected properties are declared, not guessed. Each is a **check** on the step, in the
process version, beside the step's method and exactness class. What counts as normal for a
document import is not what counts as normal for a report.

## 2. How it is verified

Four families of check are supported, and each is testable in isolation:

- **Distribution** — the value, or a statistic of the result, lies where this step's earlier
  results lie: within a band around the moving median, the same order of magnitude, the same
  sign. A monthly total ten times the previous eleven is found.
- **Completeness** — the result has every part it should: the number of records, the fields per
  record, the artifacts the step announces. An export with 412 rows where the source has 418 is
  found.
- **Reference points** — the result agrees with an independent source it must agree with: a
  control total, a second system's count, a sum that must balance.
- **Schema shape of the source** — the source the step read has the shape the step was written
  for: columns, types, order, encoding, a version marker. A partner file whose column order
  changed is found.

A check declares its method — `rule` or `statistics`, never a language model — a tolerance, and
what follows when it fails: `escalate` or `stop`.

When a check fails, the result is marked **suspect**, and the mark names the check, its family,
by how much the result deviated, and the baseline or reference it was compared against, with the
run, the step and the provenance record of the result. The suspect result opens UC-4.11. A check
never changes the result and never stops the run by itself; whether to stop is the rule of
UC-7.2.

A step of class `exact` or `sourced` carries at least one check; a bundle in which one does not
is refused at registration, with the finding naming the step. A step of class `tolerant` or
`free` may carry none, and its result is then recorded as **unchecked** — never as passed. A
process that declares no check produces no suspect mark and is visibly unchecked: silence is
never mistaken for health.

It never checks a person's work against a person's earlier work: checks are on process steps, and
a `human` step produces no result (ADR-0018, principle 14).

**Proven by:** for each family, a test process plants a violation, and exactly one suspect mark
is found, on the step that produced the result, with the right family and the right magnitude; a
result within tolerance is not marked; an `exact` step without a check does not register; the
check method is `rule` or `statistics` on every example and blueprint bundle.

## 3. Where the boundary lies

**Not covered here:** bounding since when the deviation exists and what it affected (UC-4.11),
the remediation plan (UC-4.12), the incident that tracks them (UC-6.8), and the decision to stop
(UC-7.2). This use case ends at *something is wrong, and here is what*.

**Not a model quality measure.** This is about whether a result is correct, not whether a model
is good. Evaluations are a separate mechanism and are not replaced by this.

**No repair.** Detection changes nothing. Where a correction's effect has already left Taktus, it
is anchored to a person regardless of autonomy level (ADR-0022).

**Declared properties only.** Taktus does not infer what a process ought to produce. An
undeclared property is not checked, and the absence of declarations is visible rather than
silently benign.

## 4. What it rests on

The provenance chain of ADR-0021 for the inputs a check compares against; the ledger for earlier
results; the value ledger (`0.5.0`) for distributions over time; the connector contract
(ADR-0024) for reference points in other systems; the rule of ADR-0023 for what follows a failed
check. Written first in `UC-4-result-defects.md`; the definition's `UC-4.5` asked for quality
monitoring of every process, and this is the part of it that concerns results
(`NUMBERING.md`).
