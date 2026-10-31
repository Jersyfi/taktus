# NTC-0253 — UC-15.7: a role's profile is derived from the processes

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-c--roles` (package C, concept mode, DEC-0222)
**How it follows:** the owner accepted the product outlook of 2026-10-12 (DEC-0190), which filed issue #344 as F3 for `0.7.0`: a role's profile derived from the processes, exportable as a draft position description, never a person's file, with time figures withheld below two holders and the labour-law review of DEC-0029 before use. The issue asks for the use case first. No use case required it: UC-15.6 names the role profile as outside its boundary, and UC-4.20 as a view of its own. UC-15.7 states #344 as a requirement, with its conditions made observable and two that follow from what the owner already accepted.

## 1. What was decided

UC-15.7, *A role's profile is derived from the processes it takes part in*, component
`reporting`, version `0.7.0`, the next free number of its area (`docs/usecases/NUMBERING.md`).
Its conditions are those of #344. Two follow:

- the profile is read from existing records and stores nothing of its own, because ADR-0029
  lets reporting own no figure;
- a process the reader may not see contributes nothing, and another tenant sees none of it,
  because ADR-0055 §5 and the tenant boundary hold for every read.

"Time figures are withheld" is read strictly: every figure that persons' work produced — the
time waited at the role and the steps of it performed — is withheld below two holders, as
NTC-0168 withheld a sum of waits count and all. What Taktus performs stays whole, because it is
the process's figure.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- Issue #344, *How it is verified* and *Where the boundary lies*; DEC-0190, F3.
- `docs/research/2026-10-12-market-review.md`, Zenkit idea D, §3.2.
- UC-15.6 §3, UC-4.20 §3, ADR-0015, ADR-0029, NTC-0168, DEC-0029.

## 3. What was considered

- **Amending UC-15.6.** Rejected: UC-15.6 excludes the role profile by name.
- **Withholding only time figures, as the issue's words say.** Rejected: a count of a single
  holder's performed steps is that person's output under the role's name, which NTC-0168's
  precedent withholds with the time.
- **Requiring a web page.** Left out: the issue asks for an export, not a page; a page is a new
  requirement and the owner's (mode 3).

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the owner
accepted with the product outlook. The owner may veto it within seven days of the pull request.
