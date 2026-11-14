# NTC-0295 — "Taktus never acts outward in a person's name" is a use case

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-11-14
**Raised in:** branch `area/tenant-governance` of `concept/package-f` (package F, concept mode, DEC-0239)
**How it follows:** the owner accepted ADR-0033: Taktus acts towards a service as an identity of its own, because pull requests it opened with a person's token appeared as that person's. UC-1.7 §3 states it as a boundary. The owner also accepted, in DEC-0239 §7, that the second tenant's template covers the business's catalogue and answers completely; among what always stays with a person, the business named that nobody is written to in a person's name. ADR-0264 left a gap: a step on behalf of a person could act outward with that person's credential. No use case required the rule, so nothing would hold it if the code changed. Restating what the owner already accepted as a requirement is M2.7.

## 1. What was decided

- **UC-7.12 — Taktus never acts outward in a person's name**, new, the next free number of the
  governance area (NUMBERING.md). A step on behalf of a person only reads; an outward call on
  behalf of a person is refused before the connector; a version that declares a message on such
  a step does not register. It rests on ADR-0033, ADR-0264 and ADR-0332.
- It is written beside its implementation, which concept mode admits for a use case that is new
  (DEC-0222).
- Its state is `verified`: the three named tests prove every condition of its §2.

## 2. The evidence

- ADR-0033, *Context*: every pull request Taktus opened "appeared as the owner's".
- UC-1.7 §3: "what Taktus does on its own behalf, it does as an identity of its own".
- ADR-0332 and its tests: `tests/components/run/test_on_behalf.py`,
  `tests/components/process/test_frame.py`.

## 3. What was considered

- **No use case, the ADR alone.** Rejected: an ADR says how something is built; without a
  requirement, a later change of the code could drop the rule unnoticed.
- **A line in UC-7.6.** Rejected: UC-7.6 labels a message a model wrote; who the sender appears
  to be is a separate requirement, and changing UC-7.6's sections 1 to 3 beside its
  implementation is not allowed.
- **A decision request.** Not needed: the rule follows from what the owner accepted. It adds no
  new requirement of its own.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here ADR-0033 and
DEC-0239 §7. The owner may veto it within seven days of the pull request.
