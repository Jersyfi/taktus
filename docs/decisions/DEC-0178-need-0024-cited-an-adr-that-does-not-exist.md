# DEC-0178 — NEED-0024 cited an ADR that does not exist

**Category:** DEFECT
**Raised in:** the pull request for issue #244
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

NEED-0024 said that the coding worker runs as a job in the cluster "(ADR 0034,
`deploy/k8s/README.md` §7)". There is no ADR numbered 0034: the register of ADRs skips that number, and no
file under `docs/adr/` carries it. Issue #244 repeated the reference as its source. The cluster
execution adapter is specified in `deploy/k8s/README.md` §7, and the `kubernetes` row of
ADR-0002's table is the decision it implements.

## 2. Why you are being asked

You are not. The repository named a document that does not exist: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- NEED-0024 now cites ADR-0002 and `deploy/k8s/README.md` §7.
- No gate resolves a reference to an ADR by its number; `make gate-adrs` checks each ADR's own
  file. A reference to a number nobody used passes every gate.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0178" in an issue.

## Outcome

**Corrected:** 2026-10-11
**What was wrong:** NEED-0024 cited an ADR numbered 0034 for the cluster execution adapter, and no such ADR exists.
**Why it was wrong:** the reference was written from memory of a number, and no gate resolves ADR references.
**What it now says:** NEED-0024 cites ADR-0002 and `deploy/k8s/README.md` §7.
**What changed in substance:** nothing; the adapter and its specification are what they were.
**Recorded in:** the pull request for issue #244
