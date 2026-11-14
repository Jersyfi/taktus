# DEC-0240 — Stage 5 of the software business named processes no bundle carries

**Category:** DEFECT
**Raised in:** the pull request of package F (DEC-0239), area tenant-governance
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`blueprints/software-operations/stages.yaml` named six processes in stage 5 that
`blueprint.yaml` declares not built: `b-6-05`, `b-9-05`, `b-9-08`, `b-10-05`, `b-10-06` and
`b-10-07`. It also named `b-10-03`, which no bundle carries. A stage opens only while every
process it adds runs (ADR-0191 §1), so stage 5 could never open.

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

The stages file now names only processes a bundle carries, and a test holds that.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0240" in an issue.

## Outcome

**Corrected:** 2026-11-14
**What was wrong:** stage 5 named six processes declared not built, and one name no bundle carries.
**Why it was wrong:** the rows were declared not built after the stage was written, and the stage was not carried along; no test compared the two files.
**What it now says:** stage 5 names `b-10-03-incoming-invoice` and `b-10-03-unreferenced-invoice` and no row declared not built; the blueprint's test requires every process a stage names to be carried by a bundle.
**What changed in substance:** stage 5 can open once its processes run; the rows not built stay declared so.
**Recorded in:** the pull request of package F (DEC-0239)
