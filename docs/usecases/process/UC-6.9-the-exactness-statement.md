---
id: UC-6.9
title: The exactness statement
component: process
epic: E6
serves: [P7, P8, P12]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0014: 6611f7833deb, ADR-0023: 949c6f4e13af, ADR-0029: 37c061ef032a}
supersedes: null
---

# UC-6.9 — The exactness statement

## 1. What must be achieved

A process runs. Somebody — the owner, an auditor, the person who reads the report — wants to know
how much to trust its results. "The step is `exact`" is not an answer; it is a class. The answer is
what was checked against what, what was not, and what would slip through.

Every process version carries an **exactness statement**, derived from its steps' classes and
checks and confirmed by the user in UC-4.13:

| Part | Content |
|---|---|
| **Which checks apply** | per result-producing step: its class, and for `exact` and `sourced` the checks from the catalogue with their parameters — the total reconciled against, the second system, the bounds, the threshold, the sample share |
| **What they cover** | one sentence per check, from the catalogue's row, instantiated: "every booked amount is reconciled against the invoice total read from the document store at booking time" |
| **What they do not cover** | one sentence per check, from the catalogue's row, instantiated: "an amount wrong by exactly what another amount on the same invoice is wrong by in the other direction" |
| **The residual risk** | the cases that would slip through all checks together, named; and, once the value ledger measures it, the measured rate: how many results a person corrected after the checks passed, per hundred |

The statement is visible in the dashboard, on the process page and in every run, and it is part of
every report the process delivers: a report that carries a number carries the statement of the
checks behind it, in the reader's words.

The last part matters most. A statement that ends with "what would slip through" is stronger than
one that ends with "guaranteed", because a reader can test it: they can ask whether the named
residual case has happened, and the value ledger can answer.

## 2. How it is verified

- The statement of every example bundle and every blueprint bundle renders with all four parts.
- A statement without the "does not cover" part does not render, and a bundle whose statement would
  lack it is refused.
- The statement is generated from the process version and never edited by hand. Changing a check on
  a step changes the statement in the same commit, or the test fails.
- A report fixture carries the statement of the process that produced it (`tests/exactness`,
  `tests/governance`).
- The statement never says "guaranteed correct".
- No language model writes the statement. A model may explain it to a reader, and the explanation
  names the statement it explains (ADR-0023 §4).

## 3. Where the boundary lies

**Not a certificate.** The statement says what was checked; it does not claim that the checks are
the right ones for the business, which is the user's choice in UC-4.13. **Not a figure of its own.**
The measured rate is the value ledger's; the statement reads it (ADR-0029). **Not the view.** How the
page and the report show it is `reporting`'s; the statement is the process version's.

## 4. What it rests on

UC-4.13, where the checks are chosen; the check declarations on steps (UC-4.10); the value ledger
for the measured rate (`0.5.0`); the web app (`0.3.0`) for the process page; the reports of UC-6.2;
the boundary of ADR-0014, which this statement makes visible per process. Filed under `process`
because it is generated from the process version (ADR-0029). Written first in
`UC-4-exactness-statement.md` on 2026-09-21, moved into this format in the migration's second step;
the requirement is unchanged. No version of the definition has this use case.
