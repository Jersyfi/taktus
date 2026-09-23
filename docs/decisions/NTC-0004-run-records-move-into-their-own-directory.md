# NTC-0004 — Run records move into their own directory

**Mode entry:** M2.1
**Kind:** restructuring
**Decided:** 2026-09-23
**Raised in:** [#39](https://github.com/Jersyfi/taktus/pull/39)

## 1. What was decided

`docs/first-run.md` is now `docs/runs/2026-09-19-the-run-that-stopped.md`, and `docs/runs/` is
where the record of a run lives from here on, with a `README.md` that says what belongs there
and what does not. The record of the run that completed the milestone's criterion is
`docs/runs/first-run.md`.

Nothing in the moved file changed but its name. It is the record of what was known on
2026-09-19 and it keeps saying that; its friction list is still the honest one, and two of its
items came true in the run that followed. Every reference to it in the repository now points at
the new path.

The reason for a directory rather than a second file beside the first: there will be more.
A run worth a record is not a rare event once the deployment stands — the first run on the
platform, the first run under the budget, the first run a trigger started. A directory with a
`README.md` that states the criterion for keeping one is the difference between a series of
records and a pile of files named after the day somebody wrote them.

## 2. The evidence

- The repository had one run record and nine references to it, in `README.md`,
  `tools/README.md`, the dev-orchestration blueprint's README and one of its bundles,
  `docs/status.md`, `docs/roadmap.md` twice, and three records of the register. All nine are
  redirected in the same change, and `grep` finds no reference to the old path.
- Two names for one thing were about to exist: the record of 2026-09-19 was called "the first
  run" when it was written, and the run of 2026-09-23 is the one that finished. Keeping both
  under one name would have meant rewriting the older record, which is the one thing a record
  of what was known then must not suffer.
- The older record's own friction list predicted two of the four attempts of 2026-09-23: "a
  second P-03 run for the same issue collides on the branch" and "three credentials for one
  command". A record that predicts is worth keeping addressable.

## 3. What was considered

- **Leave it where it is and put the new record beside it** (`docs/first-run.md` and
  `docs/second-run.md`). Rejected: the second name is wrong within a week, and `docs/` is
  already the directory everything lands in.
- **Rewrite the 2026-09-19 record into the new one**, one file called "the first run".
  Rejected: it would delete the state of knowledge the older record holds — what was not yet
  known, and what was expected and turned out otherwise — which is the part of a run record
  that ages best.
- **Keep the old path as a stub pointing at the new one.** Rejected: nine references were
  repointed in one change and the repository is small enough to do that. A stub is a second
  thing to keep true.

## 4. Which entry permits it

Entry M2.1 of `docs/decisions/anchors.taktus.md`: "**Documentation restructuring** without
changing what the documents say." The moved file's content is byte-identical; the new
`README.md` states a criterion for what belongs in the directory and says nothing that was not
already true of the one record it inherits. No entry of mode 3 or 4 is touched: nothing is
published under the project's name, no contract moves, no limit and no autonomy level changes.
