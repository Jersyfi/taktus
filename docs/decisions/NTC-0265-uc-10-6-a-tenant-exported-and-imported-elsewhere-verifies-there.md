# NTC-0265 — UC-10.6: a tenant exported and imported elsewhere verifies there

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-11-07
**Raised in:** branch `area/platform` of release 1.0 (concept mode, DEC-0222, DEC-0228)
**How it follows:** the owner accepted the roadmap's road to `1.0.0`, whose condition *Data export proven by re-import* reads: an export of a tenant — processes, runs, ledger, provenance, artifacts — is imported into a fresh instance, and the ledger chain and every provenance chain verify there. Principle 13 (freedom instead of vendor lock-in) asks that a business can leave with its data. No use case required it. UC-10.6 states the roadmap's condition as a requirement with its verification, and adds nothing to it.

## 1. What was decided

UC-10.6, *A tenant exported and imported into another instance verifies there*, component
`governance`, version `1.0.0`, the number release 1.0 gave this area. Its requirements are the
roadmap's sentence: what an export carries, that it goes into a fresh instance, and that the
ledger chain and every provenance chain verify there. ADR-0221 builds it.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- `docs/roadmap.md`, *The road to 1.0.0*, the row *Data export proven by re-import*.
- `docs/vision/principles.md`, principle 13.
- UC-10.5, the restore of a whole instance, which does not move one tenant.

## 3. What was considered

- **Amending UC-10.5.** Rejected: UC-10.5 restores an instance to a moment, from a backup, without
  Taktus. An export moves one tenant between two running instances, through Taktus. The two
  promises have different boundaries.
- **Leaving the roadmap row without a use case.** Rejected: a condition of `1.0.0` without a
  requirement and a verification is checked by nobody's gate.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the roadmap's road to
`1.0.0`. The owner may veto it within seven days of the pull request.
