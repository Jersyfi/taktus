# NTC-0255 — The compatibility baseline is the last release tag, and a candidate is no release

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-d--contracts` (package D, concept mode, DEC-0222), issue #396
**How it follows:** anchor M3.5 and ADR-0019 make a contract *published* once a version of Taktus that uses it is released. Anchor M1.25 separates a release candidate from a release: the session installs a candidate on the project's instance, and a release that is not a candidate stays the owner's (M3.6). A candidate therefore releases nothing to anyone outside the project, and no adapter's author built against one. The repository carries thirty-four candidate tags of `v0.2.0` and no release tag. Of the two readings consistent with the sources, the one that keeps the lane honest was taken. A lane that enforced against a candidate would make the owner's M3.5 decision for every change of `v1` before the first release, which ADR-0019 rule 2 still lets move.

## 1. What was decided

The compatibility lane (`make gate-compat`, ADR-0171 §2) compares `contracts/` with **the
highest tag `vMAJOR.MINOR.PATCH` with no pre-release part that is an ancestor of the commit
checked**. A tag with a pre-release part, `-rc.N` or `-beta`, is not a release. Until the first
release tag exists, the lane enforces nothing: it says that nothing is published, reports the
change classified against the pull request's base, and passes. A shallow clone is refused and
not read as "no release".

## 2. The evidence

- Issue #396; ADR-0096 §6 phase 4; ADR-0019 rule 2; anchors M1.25, M3.5, M3.6.
- `git tag --list 'v*'` on 2026-10-31: `v0.2.0-rc.1` to `v0.2.0-rc.34`, nothing else.
- `docs/roadmap.md`, *The road to 1.0.0*: `v1` stops moving at the freeze, the owner's act. The
  freeze record, once it exists, holds every byte regardless of this baseline (ADR-0171 §4).

## 3. What was considered

- **The newest `v*` tag, a candidate included.** Rejected: it would treat the project's own
  instance as a published consumer and fail compatible-looking work on `v1` that ADR-0019 still
  admits before a release.
- **A recorded baseline file under `contracts/`.** Rejected: every release would have to rewrite
  it, and the tag already names what was released (DEC-0027).
- **Failing breaking changes against the pull request's base before any release.** Rejected:
  it would freeze `v1` before the owner does.

## 4. Which entry permits it

M2.6: no entry of either anchor page names the baseline of a compatibility check. The decision
follows M1.25 and M3.5, which together say what a release is and when a contract is published.
A `1.0.0-beta` is a pre-release under this rule. If the owner wants the beta's contracts held,
the freeze record does it (ADR-0171 §4).

## 5. The entry it proposes

An addition to **M3.5**: *A contract is published by a release tag without a pre-release part;
a release candidate or a beta publishes none. A freeze record holds a contract regardless.* It
belongs to M3.5 because it states when that entry begins. It sets no new mode.
