# NTC-0190 — The Takt is measured at the table a run started at

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #81

## 1. What was decided

Until now a run's consumption was shown as money only. The owner gave the first weighting
table (DEC-0131) and the condition measuring must meet (DEC-0132, UC-8.5 §2). The Takt is now
measured, and charged to no one. How it is built follows ADR-0010's third amendment; these are
the choices the decisions left open:

1. **Where the table is.** The shape is `WeightingTable` in `contracts/model/v1/Model.json`,
   beside the price table, an additive definition. The tables are files under
   `contracts/model/v1/weighting-tables/`, one per version, shipped with the package. The table
   in force is the newest by `valid_from`; no setting chooses it, because the weights are the
   owner's (M4.3), not the operator's.
2. **Where the model class is set.** DEC-0131 leaves the class "per model, set by the operator".
   It is a setting, `TAKTUS_TAKT_MODEL_CLASSES`, of `model=class` pairs. The budget statement
   records the classes beside the table's digest, so that a later change of the setting does
   not change a run's Takte.
3. **What a step count weighs.** Version 0 weighs `rule` and `statistics` steps per step. An
   `llm` step is weighed by its tokens, and an `ml`, `neural` or `worker` step by its compute,
   not again by its number. A `human` or `wait` step is named as unweighed, because version 0
   gives the method no weight and nothing may count as zero.
4. **The exit code stays the money's.** `taktusctl cost <run>` exits 1 when part of the money is
   unpriced, as before. A quantity left unweighed is named in the report and does not change the
   exit code: a run with a person's approval in it would otherwise never exit 0.
5. **Where the rate is shown.** `taktusctl cost` without a run prints the tenant's Takte over
   the window of the table in force, and the Takte per hour. Every `step.finished` inside the
   window counts, weighed at the table its run started at. A run started without a table is
   named.

What changes for an operator: every run's budget statement now names a weighting table, and
`taktusctl cost <run>` prints a line `takt` and, where something is not weighed, lines
`unweighed`. The run argument is now optional.

## 2. The evidence

- `tests/components/accounting/test_takt.py`: the table in force is DEC-0131's version 0, and
  every published table's digest is pinned; a run's Takte equal the sum computed by hand from
  its recorded tokens, compute and steps, and stay the same when the configuration changes
  after it started; the Takte stand beside the money with "uncalibrated", in the text and in
  `--json`; another table and other model classes recompute them; a model in no class, a
  resource class without a weight, tokens without a model and `human` and `wait` steps are
  named; a run started without a table is named, in its cost and in the rate; the rate of two
  runs is their Takte over 720 hours.
- `tests/integration/test_first_slice.py`: the local wiring puts table 0 in force, a run of the
  first slice has Takte, and `taktusctl cost --json` without a run prints the rate.
- `tests/contract/test_shared_kernel_binding.py`: `WeightingTable` binds as the schema says.

## 3. What was considered

- **The table as an operator file, like the price table.** Rejected: the weights are the
  owner's (M4.3), and ADR-0010 requires them public in the repository. An operator file would
  let each deployment weigh differently, and a figure could no longer be compared.
- **The model class inside the table.** Rejected: model names are the operator's, and DEC-0131
  sets the class per model by the operator. A table naming models could not be published once
  for every deployment.
- **Counting `human` and `wait` steps as nothing.** Rejected: "never counted as zero" (UC-8.5).
  Naming them tells calibration that they exist.
- **A command of its own for the rate.** Rejected: UC-8.5 shows the rate beside the
  consumption, and the cost command is where consumption is read.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.2.0` item and issue #81, under DEC-0131 and DEC-0132. No contract
breaks: `WeightingTable` is a new definition, and nothing existing changes. No limit moves:
admission and the budget are untouched; a Takt figure is no budget. Nothing public is said: the
table is the owner's, and no price is stated (M4.2).
