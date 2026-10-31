# NTC-0256 — UC-14.6: a catalogue of signed adapters and bundles, in three tiers

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-d--catalogue` (package D, concept mode, DEC-0222)
**How it follows:** the owner accepted the product outlook of 2026-10-12 (DEC-0190), which filed issue #348 as F8 for `1.0.0`: a catalogue with signatures and three tiers — *reference*, *verified* in the instance's own configuration, *community* up to level 2 — that opens with the licence. The issue asks for the use case first. No use case required it: UC-14.4 names a public catalogue of third-party adapters as outside its boundary, with #348. UC-14.6 states #348 as a requirement, with its conditions made observable and three that follow from what the owner already accepted.

## 1. What was decided

UC-14.6, *A catalogue of signed adapters and bundles, in three tiers*, component `catalog`,
version `1.0.0`, the number package D gave this area (`docs/usecases/NUMBERING.md`). Its
conditions are those of #348. Three follow:

- an index never states *verified*, because ADR-0044 lets no surface take a verdict: the
  instance measures the conformance half itself;
- a pass taken before a community entry was installed does not count for it, because ADR-0044
  binds a pass to the configuration it was taken under, and an installed image is a new one;
- a community bundle becomes a proposal at level 2 or below, because a bundle has no
  conformance suite, and the gallery already holds an offered bundle to that level (ADR-0136).

The community tier's mechanism is built; the project's own index takes no outside entry until
DEC-0044 and the contributor agreement are settled, as DEC-0190 says.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- Issue #348, *How it is verified* and *Where the boundary lies*; DEC-0190, F8 and *The licence*.
- `docs/research/2026-10-12-market-review.md`, F8; UC-14.4 §3.
- ADR-0009, ADR-0012, ADR-0030, ADR-0039, ADR-0044, ADR-0136.

## 3. What was considered

- **Amending UC-14.4.** Rejected: UC-14.4 excludes the catalogue by name.
- **Letting a reference entry count as verified.** Rejected: *reference* is the project's word
  about its own adapters; ADR-0044 still asks the instance to measure the pass itself.
- **A bundle verified by its evaluation cases.** Left out: evaluation holds a change of a
  process the tenant runs (UC-4.18). A level above 2 for a bundle is a person's proposal, held
  to every check, and from level 3 every step runs only on a verified adapter (ADR-0039).

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the owner
accepted with the product outlook. The owner may veto it within seven days of the pull request.
