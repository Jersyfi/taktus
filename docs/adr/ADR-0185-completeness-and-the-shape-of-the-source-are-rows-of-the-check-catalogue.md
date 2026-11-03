# ADR-0185 — Completeness and the shape of the source are rows of the check catalogue

**Status:** accepted · extends ADR-0082 and ADR-0152 · issue #92, roadmap `0.5.0` · DEC-0223,
Option A

## Context

UC-4.10 asks Taktus to notice a result that is wrong although its run succeeded, in four
families: distribution, completeness, reference points and the shape of the source. The check
catalogue of ADR-0082 covers two of them already: distribution by its bounds, reference points
by reconciliation and agreement. Every check runs before the value counts (ADR-0152).
Completeness and the shape of the source had no row. DEC-0223 decided, Option A, that they
become rows of the one catalogue rather than a second declaration beside it: completeness with
`count` and `source`, the shape of the source with `columns` or `pattern`.

## Decision

### 1. Completeness

`{"kind": "completeness", "count": <words>, "source": <capability>}`. At the moment of the check
the run reads the count through `source`, by the read the step's work names under
`checking.reads`, as a reconciliation reads its total. The result's parts are counted: a list's
items, an object's entries, one value otherwise. The check passes when the two numbers are
equal. A count that is not a whole number of zero or more fails: nothing could be compared. The
reading joins the step's provenance record as a source input.

### 2. The shape of the source

`{"kind": "source_shape", "columns": [...], "pattern": <regular expression>}`, at least one of
the two. It judges what the step read — the step's value, or the part `checking.select` names.
The columns of a text are its first line, split at commas, semicolons or tabs, whichever it
holds; of a list of records, the fields of every record; of an object, its keys. They must be
the declared columns in the declared order. The pattern must match the value as text: a version
marker, an encoding's mark. Nothing is read from outside.

### 3. What stays as it was

Both rows are rules, never a model. A failed check fails its step with `check_failed`, and no
step after it reads the value (ADR-0152). Whether to escalate or stop afterwards is the rule's of
ADR-0023, not the check's. Each row has its words in the catalogue
(`process/domain/model/exactness.py`), so the exactness statement names what it covers and the
case that slips through.

## Alternatives

- **A second declaration for detection beside `checks`** (DEC-0223, Option B). Two vocabularies
  in every bundle. Rejected by the owner.
- **Completeness without a source: a fixed number in the bundle.** It would catch a file of 412
  rows where the bundle says 418, but not one where the source holds 419 today. The count is a
  fact of the source at the moment of the check.

## Consequences

- `contracts/shared/v1/Check.json` gains two kinds, `count` and `columns`; every existing row
  refuses both. The compatibility tool reports the two new `allOf` branches as breaking; no
  release exists, so nothing is enforced (ADR-0019 rule 2), and a document valid before is valid
  now.
- UC-4.13 names five rows and UC-4.10 its four families in words of its own. Restating them in
  the catalogue's rows is a change of the use cases, which lands apart from this implementation
  (CLAUDE.md §9).

## Where this promise ends

A check runs once, before the value counts. A check that passed then and would fail if it ran
again later — the source changed underneath the result — is not run again by itself, so it
marks nothing suspect; that is a later change (DEC-0223 names it). Completeness counts the parts
of the value, not whether each part is the right one. The shape of the source sees only what the
step read as its value: a step whose value is not what it read is judged on its value. A `sourced`
step without a check is still admitted (DEC-0223); requiring one waits for the blueprints to
carry one each.
