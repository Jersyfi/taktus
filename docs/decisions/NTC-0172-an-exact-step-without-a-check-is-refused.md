# NTC-0172 — An exact step without a check is refused

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** [#PR](https://github.com/Jersyfi/taktus/pull/PR), for issue #91

## 1. What was decided

Until now a step could be classed `exact` and say nothing about how its value is checked. Now a
process bundle registers only if every `exact` step declares at least one check, under `checks`,
from a fixed catalogue in the shared kernel. The finding for a step that declares none names the
catalogue, row by row, with what each row covers, does not cover and needs.

Every process version now has an exactness statement: which checks apply, what they cover, what
they do not cover, and the residual risk. It is generated from the version whenever it is read,
and never stored. `taktusctl exactness --process <bundle>` prints it.

Four things the use cases leave open were decided here (ADR-0082):

1. **The refusal is held at registration**, not as an invariant of every stored version, so that
   a version stored before stays readable and its runs resume.
2. **A check's parameters are its row's, and only its row's.** A parameter of another row is
   refused; a role is a role, never a person.
3. **The sentences are the catalogue's.** What a check covers and does not cover is its row's
   sentence filled in with its parameters; the only free text is the `subject`, and a statement
   that would say "guaranteed" is refused.
4. **A step without a check is named as unchecked** in every part of the statement, so that no
   part is empty and silence is never read as a check.

The sixteen `exact` steps of the example and blueprint bundles declare checks: one declares
plausibility bounds, fifteen a recomputation, on the provisional answer to DEC-0173.

## 2. The evidence

- UC-4.13 §2: "A bundle with an `exact` step and no check does not register, and the finding
  names the catalogue." UC-6.9 §2: the statement of every bundle renders with all four parts; it
  is generated and never edited; it never says "guaranteed"; no language model writes it.
- ADR-0014: "`exact` requires a machine check, and somebody has to write it."
- `tests/exactness/test_exactness_statement.py`: the refusal and its finding, every bundle's
  statement with four parts, a changed check changing the statement, the refusal of a statement
  without its "does not cover" part or with "guaranteed", and every sentence traced to its row.
- `tests/contract`: the catalogue's schema and its binding agree, and its examples hold.

## 3. What was considered

- **The refusal as an invariant of `ProcessVersion`.** Rejected: a version stored before this
  change could not be read, and recovery reads stored versions (ADR-0082 §3).
- **Requiring `checks` for `exact` in the contract's `Step.json`.** Rejected for the same reason,
  and because the contract judges one step, not a bundle.
- **A free sentence per check.** Rejected: a check could then be described as covering more than
  its row says, which UC-4.13 §2 forbids.
- **Reclassifying the fifteen steps that fit no row.** Not done here: whether they stay `exact` is
  the owner's (M3.15), asked as DEC-0173.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.5.0` item and issue #91, built on UC-4.13 and UC-6.9 as accepted with
DEC-0069. `Step.json` gains an optional field and `Check.json` is new: every step document valid
before is valid now, and `v1` is not yet released (ADR-0019). No limit or level moves. The sixth
row of the catalogue is not decided here: it is DEC-0173's.
