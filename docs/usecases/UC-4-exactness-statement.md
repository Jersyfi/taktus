# Exactness is a result, not a switch: the exactness statement

Specification for `0.5.0`, written now so that what `0.1.0` and `0.2.0` build — the exactness
classes, the checks on steps, the provenance chain — is built with its later use in view.
Nothing in this document is implemented; the version that implements each case is held to it
by tests.

The starting point is ADR-0014 and its boundary. `exact` means machine-checkable, and somebody
has to write the check; where no check can be formulated, `exact` is unreachable. Today that
boundary is a sentence in an ADR. The two cases below make it a conversation and a statement:
Taktus works through with the user how exactness is achievable for their process, and every
process then says what was checked against what, what was not, and what would slip through.
Taktus never says "this number is guaranteed correct". It says what was checked against what,
and names the case that would slip through. That makes the promise stronger, because it
becomes verifiable.

---

## UC-4.13 — Working out how a step becomes exact

**Situation.** A person designs a process, or Taktus proposes one (methods.md §5), and a step
should be `exact`: a booking amount, a payment, a tax code, a headcount. The class is not a
switch that makes the value right. It is a claim that a machine check makes it right, and the
check has to exist and has to fit the business.

**What Taktus does.** For every step that should be `exact`, before the process version is
registered, Taktus works through with the user how that is achievable and proposes checks from
a fixed catalogue. Each proposal names the check, what it covers, what it does not, and what it
needs:

| Check | What it covers | What it does not cover | Needs |
|---|---|---|---|
| **Reconciliation against a total** | the parts sum to a total another source holds: the invoice total, the bank statement, the payroll sum | a part that is wrong by an amount another part is wrong by in the other direction; a total that is itself wrong | a source for the total, read through a connector at the moment of the check |
| **Agreement with a second system** | the value equals what an independent system holds for the same thing | both systems wrong the same way; a second system fed from the first | a connector to the second system; a rule that says which one is the reference |
| **Plausibility bounds** | the value lies within bounds a rule states: a range, a sign, an order of magnitude, a ratio to last period | a wrong value inside the bounds | the bounds, stated by the user or derived by a statistic from earlier results (UC-4.10) |
| **Approval above a threshold** | a value above a threshold is confirmed by a person before it counts | a wrong value below the threshold; a person who confirms without looking | a threshold and a decider — this is a `human` step and produces no result of its own (ADR-0018) |
| **Sampling** | a stated share of results is checked by a person after the fact, and the error rate is measured | any single wrong result that was not in the sample | a share, a decider, and the value ledger to hold the rate |

The user chooses what fits their business. That is their reporting and approval regime, not
Taktus's: an organisation that reconciles against the bank statement daily and samples the
rest has made a choice Taktus records and enforces, not one it overrides. Taktus refuses one
thing only: a step classed `exact` with no check at all, because that is a promise without a
mechanism (ADR-0014). Where the user finds that no check from the catalogue fits, the step is
not `exact`; it goes to a person (`human`) or to `sourced` with the check that does fit, and
Taktus says which and why.

The conversation is a decision request of class `domain` (governance.md §3.1) when Taktus
proposes the process, and a validation finding with the same content when a person writes the
bundle by hand. Its outcome is written into the process version: the chosen checks, as `check`
declarations on the step (UC-4.10), and the statement of UC-6.9.

**What it needs.** The check catalogue as a fixed vocabulary in the shared kernel; the check
declaration on a step (UC-4.10); connectors for reconciliation and agreement; the decision
request mechanism (`0.2.0`) for the conversation.

**What it never does.** It never classes a step `exact` on its own. It never lets a language
model choose the check: the catalogue is fixed, the choice is the user's, and the check itself
is a `rule` or a `statistic`. It never presents a check as covering more than its row says.

**Proven by.** A bundle with an `exact` step and no check does not register, with the finding
naming the catalogue; every check in the catalogue has a fixture that passes and one that
fails; a check's "does not cover" is exercised by a test that slips a wrong value through it
and finds the residual risk stated (`tests/exactness`).

---

## UC-6.9 — The exactness statement

**Situation.** A process runs. Somebody — the owner, an auditor, the person who reads the
report — wants to know how much to trust its results. "The step is `exact`" is not an answer;
it is a class. The answer is what was checked against what, what was not, and what would slip
through.

**What Taktus does.** Every process version carries an **exactness statement**, derived from
its steps' classes and checks and confirmed by the user in UC-4.13:

| Part | Content |
|---|---|
| **Which checks apply** | per result-producing step: its class, and for `exact` and `sourced` the checks from the catalogue with their parameters — the total reconciled against, the second system, the bounds, the threshold, the sample share |
| **What they cover** | in one sentence per check, from the catalogue's row, instantiated: "every booked amount is reconciled against the invoice total read from the document store at booking time" |
| **What they do not cover** | in one sentence per check, from the catalogue's row, instantiated: "an amount wrong by exactly what another amount on the same invoice is wrong by in the other direction" |
| **The residual risk** | the cases that would slip through all checks together, named; and, once the value ledger measures it (`0.5.0`), the measured rate: how many results a person corrected after the checks passed, per hundred |

The statement is generated from the process version and never edited by hand: a change to a
step's class or checks changes the statement, and a statement that says something the version
does not do is impossible. It is **visible in the dashboard** on the process page and in every
run, and it is **part of every report** the process delivers: a report that carries a number
carries the statement of the checks behind it, in the reader's words.

The last part matters most. A statement that ends with "what would slip through" is stronger
than one that ends with "guaranteed", because a reader can test it: they can ask whether the
named residual case has happened, and the value ledger can answer.

**What it needs.** UC-4.13; the check declarations on steps (UC-4.10); the value ledger for the
measured rate; the web app (`0.3.0`) for the dashboard; the reporting of area 6 for the report.

**What it never does.** It never says "guaranteed correct". It never omits the "does not
cover" part; a statement without it does not render. It never lets a language model write the
statement — a model may explain it to a reader, and the explanation names the statement it
explains (ADR-0023 §4 applies).

**Proven by.** The statement of every example bundle and every blueprint bundle renders with
all four parts, and a bundle whose statement would lack the "does not cover" part is refused;
changing a check on a step changes the statement in the same commit or the test fails; a
report fixture carries the statement of the process that produced it (`tests/exactness`,
`tests/governance`).
