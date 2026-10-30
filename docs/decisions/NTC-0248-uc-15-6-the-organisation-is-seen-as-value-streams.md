# NTC-0248 — UC-15.6: the organisation is seen as value streams

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-30
**Raised in:** branch `concept/package-b--views` (package B, concept mode, DEC-0222)
**How it follows:** the owner accepted the product outlook of 2026-10-12 (DEC-0190), which filed issue #338 as F1 for `0.6.0`: a tenant's processes shown as value streams with role swimlanes and department crossings, a value stream an object of its own extending UC-15.4's chain. The issue asks for the use case first. No use case required it: UC-15.4 declares a chain but no view of the organisation, and UC-9.7 shows one process. UC-15.6 states #338 as a requirement, with its conditions made observable and two that follow from what the owner already accepted.

## 1. What was decided

UC-15.6, *The organisation is seen as value streams, not as an org chart*, component
`reporting`, version `0.6.0`, the next free number of its area (`docs/usecases/NUMBERING.md`).
Its conditions are those of #338: the view reads only existing records and stores nothing of its
own, `org_path` stays and is overlaid, and no figure names a person. Two follow:

- a changed declaration keeps the revision before, because CLAUDE.md §9 forbids deleting a
  definition's history without asking;
- a role's waiting is shown only where at least two identities hold the role, because ADR-0015
  withholds a figure that would be one person's.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- Issue #338, *How it is verified* and *Where the boundary lies*; DEC-0190, F1.
- `docs/research/2026-10-12-market-review.md`, Zenkit ideas A and C, and the screen of §3.3.
- UC-15.4 §2, UC-9.7 §2, ADR-0015, ADR-0029, ADR-0146.

## 3. What was considered

- **Amending UC-15.4.** Rejected: UC-15.4 requires the handover between processes, for
  `0.7.0`. The view and the stream's own fields are a requirement of their own, and this use case
  names UC-15.4's chain as what it extends.
- **The role profile and the simulation of the outlook's screen.** Left out: the issue does not
  ask for them, and a new requirement is the owner's (mode 3).

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the owner
accepted with the product outlook. The owner may veto it within seven days of the pull request.
