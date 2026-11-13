# NTC-0279 — An artifact is unmaintained against the project, and a scaffold furnishes only from production

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** the branch `concept/final-1-0`, for DEC-0236
**How it follows:** UC-13.2 asks that a check names every artifact that is "no longer
maintained", and says no more about when that is. It asks that a scaffold passes "the same
evaluations and the same approval as a learned skill". Principle 14 forbids assessing a person,
and principle 9 forbids findings nobody can act on; ADR-0162 lets nothing outward act before
production. Where two readings were both consistent with these sources, the stricter in
substance and the sparer in ceremony was taken (CLAUDE.md §8).

## 1. What was decided

- **Unmaintained is measured against the project.** An artifact is unmaintained when the
  project's newest change lies more than the artifact's `maintained_days` after the artifact's
  own last change. The project's newest change is the commit the check read the repository at,
  or a page's change where that is later. The calendar is not read.
- **The windows of the shipped scaffolds** are the scaffold's own declaration: use cases 90
  days, architecture decisions 180, test strategy 180, definition of done 365; takeover
  instructions 60, process description 90, evaluation cases 180, anchors 365; data sources 30,
  findings 60, method 90. The question of an analysis and every page declare none: they are
  checked for presence only.
- **A check reads a draft; furnishing needs production.** A check reads and writes nothing
  outside, so it reads the scaffold at its version in production, or else at its newest version
  that is neither retired nor private, and names that stage. Furnishing writes into the
  organisation's systems, so only a version in production furnishes a project.
- **Repository artifacts arrive as a pull request.** Taktus does not put them onto the
  project's branch itself; a person merges them.

## 2. The evidence

- A project nobody works on keeps its artifacts as they were. Against the calendar, every one of
  them would turn stale and be named, though nothing changed that they describe.
- The windows follow how fast each artifact goes out of date: a list of data sources faster than
  a definition of done. They are a scaffold's declaration, and an organisation's own scaffold
  sets its own.
- A curated skill that writes into the organisation's systems before it was evaluated would be
  the one skill that acts outside without the lifecycle's approval.
- UC-13.2 says Taktus creates the artifacts "together with the person". A pull request is the
  act by which the person accepts them.

## 3. What was considered

- **Staleness against the calendar.** Rejected: findings for a project at rest that nobody can
  act on.
- **One window for every artifact.** Rejected: a list of sources and a definition of done do
  not age alike.
- **Furnishing from any stage.** Rejected: a curated skill would act outside before approval.
- **Committing onto the project's branch directly.** Rejected: the structure would be put in
  place without the person.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

M1.28, a mode-1 entry: how long a scaffold's artifact may stay unchanged is the scaffold's own
declaration, measured against the project's newest change.
