# DEC-0020 — A branch the connector writes loses the file mode

**Category:** DEFECT
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), which corrects it after the first live run met it
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

When P-03 Implementation puts a coding worker's change on a branch, the run calls the
repository connector's operation `repository.branches.create`. The connector writes each
changed file as a new blob and then one tree entry per file. A tree entry carries the file's
**mode** — whether it is a plain file, an executable, or a symbolic link — and the connector
wrote the same mode for every entry: `100644`, a plain file.

The effect: **a file that was executable in the base stops being executable the moment a
change touches it.** Nothing warns; the branch looks right in a diff, which does not show the
mode unless one asks for it.

The first live run of 2026-09-23 met it head on. The coding worker's change to issue #11 was
correct and touched `tools/preflight.sh`, which every `make` target of this repository runs
through `need-<tool>`. On the branch, that file arrived as a plain file. Every job of the
pipeline then died on its first line:

```
make: tools/preflight.sh: Permission denied
make: *** [Makefile:11: need-uv] Error 127
```

The pipeline reported `failure`, P-03's step `verify` refused the change, correctly, and the
run escalated without opening a pull request. The verdict was right about the pipeline and
wrong about the change: the change was fine and the branch was not.

## 2. Why you are being asked

You are not. The connector's own documentation says it puts the given files on a branch; it
does not say it flattens their modes, and no reader would expect a write of a file's content
to change what the file is. Entry M1.4 of `docs/decisions/anchors.taktus.md` makes the
correction the session's, recorded here. The correction makes the connector right, not the
gate weaker: nothing in the pipeline was touched.

## 3. What you must decide

Nothing. The correction is made, with a test that fails without it.

## 4. What you need to know to decide

- The mode is read from the base tree before the new tree is written: one request for the
  whole tree, and for a tree too large to come in one answer, a walk along the directories of
  the paths that were missing. A file the base does not have is written as a plain file.
- Only the three modes a blob may carry are preserved — a plain file, an executable, a
  symbolic link. Anything else the base carries, a submodule, cannot be written back as a blob
  and gets the plain file mode.
- The cost is one request per branch write in the ordinary case, counted in the operation's
  consumption like every other.
- The test that would have caught it is
  `tests/adapters/connectors/test_repository_actions.py::test_a_changed_file_keeps_the_mode_it_had`:
  a base branch of the fake service carrying an executable, a change to it, and the mode read
  back from the tree the connector wrote. It fails on the old code.

## 5. Options

None for the owner. What the session did: read the base tree's modes and carry them forward;
said so in the connector's README and in the operation's own summary, which is what a process
author reads; added the test.

**What this does not cover, deliberately:** a file that is *new* and should be executable. The
worker's changeset artifact carries a path, its content and its encoding, and has no way to
say "this one is executable", so the connector has nothing to carry forward for a new path.
That is a second, unobserved gap in a second place — the worker contract's changeset — and it
is raised as its own issue rather than built speculatively here. A script this repository
gains would today arrive as a plain file, and the same `Permission denied` would follow; the
issue says so.

## 6. What is blocked

Nothing any more. The first live run was, until this correction: every pipeline job on the
branch failed before running a check. The run was repeated after it.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0020" in an issue, with the
reading you hold.

## Outcome

**Corrected:** 2026-09-23
**What was wrong:** `repository.branches.create` wrote every tree entry with mode `100644`, so
a file that was executable in the base stopped being executable on the branch. The first live
run's branch carried `tools/preflight.sh` as a plain file and every pipeline job failed with
`Permission denied` before running a single check.
**Why it was wrong:** writing a file's content is not a statement about what the file is. A
verdict that is red because the write broke the tree is not a verdict about the change, and
P-03 reads that verdict as the gate before it opens a pull request — so the defect turned a
correct change into a refused one.
**What it now says:** a file keeps the mode it has in the base — an executable stays
executable, a link stays a link — read from the base tree before the new tree is written; a
file the base does not have is a plain file, and the operation's input has no way to say
otherwise. The connector's README and the operation's summary say it, and a test holds it.
**What changed in substance:** the tree entries the connector writes for files that exist in
the base, and one request per branch write to read their modes. Nothing else: the same blobs,
the same commit, the same mark, the same idempotency.
**Recorded in:** [#26](https://github.com/Jersyfi/taktus/pull/26)
