# NTC-0257 — UC-10.5: an instance is restored to a chosen moment, and every chain verified

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-d--recovery` (package D, concept mode, DEC-0222)
**How it follows:** the owner accepted the DevOps review of 2026-10-12 (DEC-0187), which filed issue #346 for `1.0.0`: an operator may enable WAL archiving for point-in-time recovery, and each install profile states its recovery point and recovery time objective, proven by the restore drill. *The road to 1.0.0* names that drill, S-03, and its check: every tenant's chain verifies against a digest taken before, not that the database starts. No use case required either: UC-10.1 asks that Taktus runs anywhere, UC-4.12 that a remediation plan is executable by hand. UC-10.5 states #346 and the road's condition as a requirement. Where the issue left a reading open, the stricter one in substance was taken (CLAUDE.md §8).

## 1. What was decided

UC-10.5, *An instance is restored to a chosen moment, and every chain verified*, component
`governance`, version `1.0.0`, the number given to this area. Three readings were settled, and
ADR-0174 builds them:

- **"Verifies" means recomputed without Taktus.** The drill recomputes every chain by the
  ledger's published rule. A check through Taktus's own code would let a faulty Taktus confirm
  its own restore, against ADR-0013 C.
- **"A digest taken before" is the backup's manifest, and for a moment the heads noted at it.**
  The manifest's heads must each be in the restored chain; heads noted at the moment must be
  the newest entries exactly.
- **The recovery time objective has a person's part, which is not measured.** Only the
  machine's part is measured, by every drill, and bounded.

## 2. The evidence

- Issue #346, *What must be achieved*, *How it is verified* and *Where the boundary lies*;
  DEC-0187; `docs/research/2026-10-12-devops-review.md` §K2.
- `docs/roadmap.md`, *The road to 1.0.0*, the condition *A restore drill that verifies the
  ledger chain*; ADR-0013 C and D; ADR-0087; ADR-0006, ADR-0164.

## 3. What was considered

- **Amending UC-10.1.** Rejected: UC-10.1 is about where Taktus runs; a restore to a moment is
  neither, and UC-10.1 keeps its state.
- **A drill that checks the database starts and the heads match.** Rejected: the road names
  exactly this as not enough.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the owner
accepted with the DevOps review and the roadmap's condition. The owner may veto it within seven
days of the pull request.
