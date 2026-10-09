# NTC-0065 — A pointer in the vision's history follows a deleted file

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** [#136](https://github.com/Jersyfi/taktus/pull/136)
**How it follows:** M4.5 keeps what the vision layer says with the owner: what Taktus is for, the principles, the personas, the non-goals. A sentence that names the file in which two open points were carried says none of that; it says where to look. The migration's working file said that it is deleted at the migration's end, and the issue of this step (#63) asks that nothing point at it afterwards. Strict in substance: no statement of the vision changes, including one that is now out of date; sparing in ceremony: one sentence, recorded here, instead of a request about a pointer.

## 1. What was decided

`docs/vision/history.md`, in its account of the original architecture chapter, said that the skill format
and the distinction between command and rollout channels "are carried in `docs/usecases/MIGRATION.md`".
That file is deleted by this pull request. The sentence now says that both were carried by the
migration's working file, deleted at its end, and that where each stands now is in UC-14.2 and UC-12.1.

Nothing else in `docs/vision/` was changed. The sentence before it, which says that the distinction
between the two kinds of channel is not written down, is left as it is: UC-12.1 and UC-1.7 have written
it down since, and saying so changes what the vision layer states, which is the owner's (M4.5).

## 2. The evidence

- The deleted file's own words: "When the migration is complete it is deleted, and nothing here survives
  except in the files it points to."
- UC-14.2 names the skill format as missing an ADR; UC-12.1 holds the distinction between command and
  rollout channels (step 3, #132).
- `git log -- docs/vision` shows no change to the vision layer since it was brought in (#46).

## 3. What was considered

- **Leaving the pointer.** Rejected: it would point at a file that no longer exists, which the issue of
  this step forbids.
- **A decision request about one sentence.** Rejected: the owner is asked what the vision says, and this
  sentence says where to find something, not what is so.
- **Also correcting the out-of-date sentence before it.** Rejected: that changes what the history states;
  it is noted in the pull request for the owner instead.

## 4. Which entry permits it

None of mode 1 or 2 names a pointer inside `docs/vision/`; M4.5 names the vision's content. M2.6 applies:
decided in the direction of M4.5, which this keeps whole.

## 5. The entry it proposes

**M1.13** — *A pointer in `docs/vision/` to a file that moved or was deleted* is updated to where its
content now lives, with no change to what the vision states; a statement that has become untrue is raised
to the owner (M4.5), not corrected.
