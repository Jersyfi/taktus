# NTC-0260 — UC-13.7: every role finds its way in one measured design system

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-11-04
**Raised in:** branch `concept/package-e--ui` (package E, concept mode, DEC-0227)
**How it follows:** the owner asked in DEC-0227 item 3 for the web app to be redesigned from the roles that use Taktus, with colours following his design system so that one design system serves all his applications, keeping principle 7 (transparency fitted to the role) and principle 14 (people at the centre). No use case required it: UC-6.10 requires the distinctions of the live representations, not how a reader finds a page or whether a colour is readable. UC-13.7 states the owner's request as a requirement. Where the request left a reading open, the stricter one in substance was taken (CLAUDE.md §8).

## 1. What was decided

UC-13.7, *Every role finds its way in one measured design system*, component `reporting`,
version `0.6.0`, the number given to this area. Three readings were settled, and ADR-0177 and
ADR-0178 build them:

- **"Serves every role" means an order, not a permission.** The destinations are grouped by what
  each persona of `docs/vision/personas.md` tries to do, and every reader sees all of them. That
  file says a persona is not a permission set; the surface keeps deciding what a reader reads.
- **"Colours following the design system" means its tokens, copied unchanged.** Taktus adds a
  layer of its own, and every value in it references the design system's primitives.
- **"Readable" means measured.** Contrast is a test in both modes, at the WCAG 2.2 thresholds.

## 2. The evidence

- DEC-0227, *What it changes*, item 3; `docs/vision/personas.md`; `docs/vision/principles.md`,
  principles 7 and 14.
- UC-6.10 and ADR-0059 (distinctions carried by form, never by colour alone); M1.20 and DEC-0185
  (the look is the session's within those distinctions).

## 3. What was considered

- **Amending UC-6.10.** Rejected: UC-6.10 requires what a representation shows, not how a reader
  reaches it, and it keeps its state.
- **One start page per role.** Rejected: the web app does not know a reader's persona, only what
  the surface lets them read. A start page ordered by what waits for the reader serves every role
  without guessing one.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here DEC-0227 item 3. The
owner may veto it within seven days of the pull request.
