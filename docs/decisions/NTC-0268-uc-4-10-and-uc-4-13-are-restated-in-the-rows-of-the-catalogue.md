# NTC-0268 — UC-4.10 and UC-4.13 are restated in the rows of the catalogue

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-11-07
**Raised in:** branch `area/remainders` of `concept/release-1-0` (release 1.0, concept mode, DEC-0228)
**How it follows:** the owner answered DEC-0223 with Option A: completeness and the shape of the source become rows of the one catalogue, every check runs before the value counts, and what follows a failed check is the rule's of ADR-0023, not the check's. The option names its consequence: "UC-4.10 is restated in the catalogue's rows in a change of its own; UC-4.13 gains two rows". ADR-0185 built the rows. Both use cases still speak in the words they had before.

## 1. What was decided

The two use cases are restated, and nothing they require moves beyond what DEC-0223 accepted:

- **UC-4.13 §1** gains the three rows the catalogue holds besides its five: recomputation
  (DEC-0173), completeness against a count another source holds, and the shape of the source
  (DEC-0223), each with what it covers, what it does not cover and what it needs, in the words of
  `components/process/domain/model/exactness.py`. **§3** says "eight rows" where it says "five".
  **§2** keeps "Taktus refuses this one thing only" for the conversation about `exact`, and
  names UC-4.10 for the refusal of a `sourced` step without a check.
- **UC-4.10 §2** names each family by its rows: distribution by plausibility bounds, their
  bounds derived by a statistic from earlier results; completeness by completeness against a
  count; reference points by reconciliation against a total and agreement with a second system;
  the shape of the source by its row. A check declares its row's parameters; whether a failure
  escalates or stops is the rule's (ADR-0023, UC-7.2). A check runs before the value counts, and
  a value that fails it does not count (ADR-0152); a check that reads a source and is applied
  again after the result counted marks it suspect (ADR-0179). The sentence "a check never
  changes the result and never stops the run by itself" stays for the check applied again.

**The restatement is not in this pull request, and why.** `make gate-usecases` refuses a pull
request that changes a use case's sections 1 to 3 and touches its implementation. In concept
mode only a use case that is new is exempt (DEC-0222): `tools/check_usecases.py` admits a
changed requirement beside its implementation on a `concept/` branch only when the use case is
new. The concept branch touches `src/taktus/components/process/` and
`src/taktus/components/run/` and the tests both use cases name — this area's refusal of a
`sourced` step without a check among them — so the gate refuses the restatement here. It lands in
a pull request of its own after release 1.0 merges, with the text above; until then the use
cases' words lag the catalogue they describe, and the code is held to ADR-0185 and ADR-0233.

## 2. The evidence

- DEC-0223, Outcome: "Option A".
- ADR-0185, *Consequences*: "Restating them in the catalogue's rows is a change of the use
  cases, which lands apart from this implementation".
- UC-4.13 §5: "Section 3 still speaks of five rows; restating it is a change of the use case of
  its own".

## 3. What was considered

- **Restating them here.** Refused by the gate, rightly: the rule protects a requirement from
  being adjusted by the change that implements it (CLAUDE.md §9).
- **A decision request.** Not needed: the owner already chose the option that names this
  consequence. A new requirement would be one; this is none.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here DEC-0223, Option A.
The owner may veto it within seven days of the pull request.
