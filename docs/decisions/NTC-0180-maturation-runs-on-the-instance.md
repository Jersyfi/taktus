# NTC-0180 — Maturation runs on the instance, from the command line and on a schedule

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #229

## 1. What was decided

Until now the handlers of method maturation existed and were tested, and nothing on an instance
called them (ADR-0084). They are now reachable in three ways (ADR-0086):

1. **`taktusctl maturation measures`** prints every step's measures — cost per case at the
   instance's price table, duration, corrections, spread. No measure names a person.
2. **`taktusctl maturation correct`** records a person's correction of a step's result, as the
   identity the command names. A step without a result is refused, with the reason.
3. **`taktusctl maturation propose`** asks for proposals, each training and each trial held to
   the budget the command names, and prints every outcome: the request raised, or why not.
4. **S-06 Maturation**, a process of `blueprints/self-operation/`, runs the measures and the
   proposals weekly, through the elected scheduler, once per slot. It reaches them through the
   loopback connector's new capability `orchestrator.maturation`.
5. **Both are wired with the instance's price table and its decision port.** Without a price
   table, every cost is named unpriced and no candidate is trained: no cost could be compared,
   so no proposal could rest on one. Before, a candidate was trained and then not proposed.

## 2. The evidence

- Issue #229, section "How it is verified", each condition a test:
  `tests/integration/test_maturation_command.py` (the measures read back from a run history
  the test wrote, naming nobody; a correction recorded as the identity named; a step without a
  result refused with the reason; proposals asked for under a budget, every outcome printed);
  `tests/integration/test_time_triggers.py` (S-06 started once per weekly slot with two
  schedulers); `tests/composition/test_maturation_wiring.py` (a proposal raised through the
  instance's decision port by way of the loopback; without a table, every cost unpriced and
  nothing trained or proposed).
- ADR-0084, *Consequences*: "Nothing calls the handlers on a schedule or from the command line
  yet: #229."

## 3. What was considered

- **A schedule in the instance's environment.** Rejected: a second way for the scheduler to
  start work beside the triggers of registered processes, without a run in the ledger or a
  report; S-01 and S-05 are the precedent for a self-operation process.
- **Keeping the training without a price table.** Rejected: its verdict is known before it
  starts, and it spends the budget for nothing.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.4.0` item and issue #229. No contract changes: the loopback's
declaration is the adapter's own, and S-06 is a bundle. No limit moves: every training and trial
is held to the budget a person or the trigger names. S-06 runs at level 3, as S-01 and S-05 do,
and nothing it proposes is applied: the move stays a person's decision (M3.13). What maturation
must require is still DEC-0164, open; nothing here answers it.
