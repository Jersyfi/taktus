# DEC-0241 — The first-install guide told the reader to wait for a release that never finishes

**Category:** DEFECT
**Raised in:** the pull request of package F (DEC-0239), area tenant-governance
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`docs/guides/administration/first-install.md` §3.4 told the reader to install the chart with
`helm install --wait`. `deploy/k8s/README.md` §10 says that on a first install `--wait` never
finishes: the database is created by the chart and the migrations run as a hook after it, so the
roles cannot be ready before the release ends (DEC-0060).

## 2. Why you are being asked

You are not. The repository contradicted itself: entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

The guide now follows the deployment README.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0241" in an issue.

## Outcome

**Corrected:** 2026-11-14
**What was wrong:** the guide's install command carried `--wait`.
**Why it was wrong:** the guide was written from the general Helm habit, not from the chart's own install order.
**What it now says:** install without `--wait`, then wait for the migration job and the roles, as `deploy/k8s/README.md` §10 says.
**What changed in substance:** nothing in the software; a reader following the guide no longer waits for a command that does not end.
**Recorded in:** the pull request of package F (DEC-0239)
