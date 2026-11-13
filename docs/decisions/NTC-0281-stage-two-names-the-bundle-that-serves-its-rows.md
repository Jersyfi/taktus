# NTC-0281 — Stage 2 names the bundle that serves its rows, and leaves out what is not built

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** branch `area/ops1` (final round before 1.0, concept mode, DEC-0222), for issue
#401
**How it follows:** ADR-0191 §1 opens a stage only once every process it adds runs. NTC-0263
and NTC-0266 place B-3.03, B-3.12 and B-4.01 to B-4.06 inside B-3.02's bundle. Until now a
tenant's plan had to name `b-3-02` for them. The shipped stage 2 therefore never opened as
declared. `blueprint.yaml` now declares each row without a bundle: `served_by` names the
bundles that carry it, and `not_built` marks a row nothing serves. NTC-0280 left out of every
stage the rows the instance serves. The same reasoning applies here. A stage names what serves
its rows, and it leaves out what nothing serves. Strict in substance, sparing in ceremony: the
condition is unchanged, and the stage counts only what runs.

## 1. What was decided

- Stage 2 of `blueprints/software-operations/stages.yaml` names `b-3-02` for B-3.03, B-3.12 and
  B-4.01 to B-4.06. It no longer names them one by one. B-3.02's level stays 3.
- B-4.07, a document of the business declared `not_built`, stands in no stage until a bundle
  serves it.
- Every stage of the blueprint can now be declared as shipped.

## 2. The evidence

- `tests/governance/test_stages_shipped.py`:
  - stages 0 to 2 name only shipped bundles;
  - stages 0 to 2 are declared as shipped, every process is registered from its shipped bundle,
    and a ledger that meets stage 2's condition opens stage 3.
- `tests/governance/test_stages.py`: 77 processes of UC-03 §4.1 to §4.10 stand in a stage, and
  none of the rows served inside B-3.02 or not built does.

## 3. What was considered

- **Keeping the rows and leaving the change to each tenant's plan, as NTC-0263 did.** Rejected:
  the shipped stage never opened, and every tenant would repeat the same edit.
- **A process `b-4-07` that reminds of the policy.** Rejected: it would be a bundle without a
  source, built only to fill a stage.

## 4. Which entry permits it

M2.6, with NTC-0263 and NTC-0280 as precedent. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond NTC-0280's counterpart of M2.13.
