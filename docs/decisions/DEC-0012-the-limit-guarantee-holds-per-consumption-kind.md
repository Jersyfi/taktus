# DEC-0012 — The limit guarantee holds per consumption kind

**Category:** DEFECT
**Raised in:** [#13](https://github.com/Jersyfi/taktus/pull/13), which adds the action half of the connector and the first end-to-end
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Taktus runs work in steps and keeps a budget for every run: so much money, so many requests of
a quota, so many seconds of compute. Before a step starts, Taktus asks the worker what the step
will need and lets it start only if that fits what is left. The architecture promised, without
qualification, that a limit is therefore never breached.

The promise depends on one thing: at every step boundary Taktus must know exactly how much has
been used so far. For tokens, quota and compute seconds it does, because every worker reports
those per step. For money it does not always: the first real coding worker learns what an
assignment cost only when the assignment ends, and reports it then. Within an assignment, the
running total in money is an estimate. A step that costs more than it was estimated at is
discovered when the assignment finishes, and by then the money is spent.

The worker's own documentation said so. The architecture decision that made the promise did
not know about it. A limitation stated where a worker is described is not the same as a promise
that names its own boundary.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies: what the software does does not change. It
admits steps against estimates and running totals exactly as before; what changes is that the
decision record now says for which quantities the running total is exact and for which it is
not. That is row D6 of §2: the repository's documents disagreed with each other — one promised
without qualification, another documented the exception — and the disagreement is corrected
and recorded here.

## 3. What you must decide

Nothing. The record exists so that a reader of the decision finds its boundary in the decision,
not in a worker's README, and so that a budget in a currency is never sold as a guarantee it
cannot be.

## 4. What you need to know to decide

- **Step.** One unit of work of a run. Results are saved per step, so that a run can stop and
  resume at a step boundary.
- **Admission.** The check before a step starts: its estimated need against what is left of the
  budget. A step that does not fit does not start; nothing is aborted.
- **Consumption kinds.** What a step can use: tokens (what a language model reads and writes),
  quota (units of a subscription window or a request allowance), compute (seconds in a resource
  class), currency (money).
- **Per step versus per assignment.** A worker that reports a quantity after every step gives
  Taktus an exact running total. A worker that reports a quantity only when the whole assignment
  ends gives Taktus an exact total only at that moment; in between, Taktus has the estimate.
- **Takt.** The normalised unit of orchestrated work (ADR-0010, proposed). It derives from
  tokens and compute seconds, both reported per step, and not from money. A budget in Takte
  therefore has the guarantee a budget in a currency does not. That consequence was not in
  ADR-0010 and is now stated in ADR-0005's amendment.

## 5. Options

None for the owner. What the session did: amended ADR-0005 with a table of consumption kinds
and the guarantee each carries; stated in plain words what a person setting a currency budget
can and cannot expect; corrected `docs/architecture/control-plane.md` §5.1 and §7 to say the
same; and recorded the consequence for the Takt.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0012" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-19
**What was wrong:** ADR-0005 promised "no limit is ever breached" for every consumption kind,
while the coding worker's README stated that money is reported once per assignment and that a
currency limit therefore works against the estimate, not against a running total; the two
documents disagreed and the decision record was the one that was wrong.
**Why it was wrong:** the guarantee comes from admission, and admission needs an exact running
total at every step boundary; a quantity reported only at the end of an assignment has no such
total within the assignment, so a step that overshoots its estimate is discovered when the money
is already spent.
**What it now says:** ADR-0005 carries an amendment with a table — tokens, quota and compute
seconds are reported per step and the guarantee holds; currency reported per assignment
degrades to an estimate, and the budget can be exceeded by the difference between one
assignment's estimate and its actual cost, visible in the ledger at the boundary where it was
reported; a person setting a currency budget can expect that no assignment starts whose estimate
does not fit, and cannot expect that a running assignment is stopped by its cost. The Takt
derives from tokens and compute, not from money, and is therefore the quantity admission control
can hold a run against. `control-plane.md` §5.1 and §7 say the same.
**What changed in substance:** nothing the software does. Admission checks estimates against
running totals as before; the record now states which totals are exact.
**Recorded in:** [#13](https://github.com/Jersyfi/taktus/pull/13)
