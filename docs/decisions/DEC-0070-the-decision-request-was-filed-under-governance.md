# DEC-0070 — The decision request was filed under governance

**Category:** DEFECT
**Raised in:** [#61](https://github.com/Jersyfi/taktus/issues/61), while filing UC-7.4
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The plan for moving the project definition into the repository said that every use case of the
governance epic goes into the governance folder, and that UC-7.4, the decision request, "is largely
built". Both were wrong for UC-7.4.

A use case is filed in the folder of the component whose code implements it, so that a change to
that code can be checked against the requirement. Decision requests and their register belong to
the `decision` component, not to `governance`. Filed under governance, a change to the code that
implements decision requests would not have been recognised as touching UC-7.4.

The decision request is built for this repository, as a set of files and a check run by hand. In
the product, the `decision` component has no code yet.

## 2. Why you are being asked

You are not. The repository said something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- UC-7.4 is filed under `decision/`, where `docs/usecases/README.md` and
  `docs/architecture/project-structure.md` §1 put it: the folder named as the component that owns
  decision requests.
- `MIGRATION.md` now says so, and says that the decision request is built for this repository by
  hand and not in the product. UC-7.4's state is `specified`.
- No requirement changed: where a use case is filed decides nothing about what it requires.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0070" in an issue.

## Outcome

**Corrected:** 2026-10-08
**What was wrong:** `docs/usecases/MIGRATION.md` filed UC-7.4 under `governance/` with the rest of
its epic, and called it largely built.
**Why it was wrong:** the table was written by epic, and an epic is not a component; the decision
request's code belongs to `decision`, and what is built of it is this repository's register, not
the product's mechanism.
**What it now says:** UC-7.4 is in `docs/usecases/decision/`; it is built for this repository by
hand, and nothing of it is in the product.
**What changed in substance:** nothing; the use case was written in the right folder from the start.
**Recorded in:** [#61](https://github.com/Jersyfi/taktus/issues/61)
