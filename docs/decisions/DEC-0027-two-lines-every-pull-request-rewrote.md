# DEC-0027 — Two lines every pull request rewrote

**Category:** DEFECT
**Raised in:** [#46](https://github.com/Jersyfi/taktus/pull/46), which corrects it
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The status file, `docs/status.md`, is the one file that says where the project stands. On
2026-09-27 four pull requests that each changed it could not be merged cleanly one after the
other. DEC-0026 found two causes and fixed them: pull requests had been built on each other's
branches, and the file stored a generated list of what was open.

A third cause stayed. The file began with an `As of` date, and the gate that checks the file failed
when that date was older than the newest decision record. So every pull request that raised a
record had to rewrite the date — the same line, every time. And section 1 carried a paragraph,
*Decided since the last version*, to which every pull request that decided something added its
sentence — the same paragraph, every time. Any two pull requests open at once conflicted on those
two places, whatever else they did. Pull request #38, opened by Taktus itself on 2026-09-23, still
conflicts with `main` on exactly the date line.

## 2. Why you are being asked

You are not. The repository says that nothing generated is stored in a file pull requests edit by
hand, and that pull requests must be mergeable in any order; a gate that forced every pull request
to rewrite the same line contradicted both. That is a documentation defect, entry M1.4 of
`docs/decisions/anchors.taktus.md`, and fixing the cause of the conflicts was asked of the session
in mode 1.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- **The date said nothing the history does not.** The date a file last changed is the date of its
  last commit, which the host shows beside the file. The stored copy could only be the same or
  wrong.
- **The date check caught nothing the other check does not.** Its purpose was that a status written
  before a decision cannot account for it. But every decision record is a file under
  `docs/decisions/`, and a change there already fails the gate unless the status file is touched in
  the same pull request. Removing the date check therefore loses no case; the demonstration is
  NTC-0005.
- **The paragraph was a list.** *What was decided since the last version* is the register's index,
  newest last, with the pull request of each. A list kept by hand beside it is a copy.

## 5. Options

None for the owner. Three were weighed:

- **Generate the file on `main` after every merge.** Rejected, as in DEC-0026: CI here validates and
  never writes; a commit pushed by the workflow starts no CI of its own and would reach `main`
  unchecked.
- **Keep the date, but let the gate write it.** Rejected: the written date is still a line every
  branch changes, and the conflict is the same.
- **Store neither** — chosen. The file has no date line and no running list. The gate fails a file
  that carries either, naming this record, so that the lines do not come back one pull request at a
  time. What is left in the file is prose each pull request changes only where the state it
  describes changed; two pull requests then conflict only when they describe the same thing
  differently, which is a conflict a person should resolve.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0027" in an issue, with the reading you hold.

## Outcome

**Corrected:** 2026-09-29
**What was wrong:** the status file carried an `As of` date that the status gate required to be no
older than the newest decision record, and a running paragraph of what had been decided since the
last version; every pull request rewrote both, so any two conflicted on them.
**Why it was wrong:** a line that every change must rewrite is a conflict between every pair of
changes. The date copied what the commit history holds; the paragraph copied what the register's
index holds.
**What it now says:** `docs/status.md` has no date line and no running list of decisions;
`make gate-status` fails a file that carries either, and no longer compares a date with the
register, because a new record already requires the file to be touched. ADR-0028 §3 is amended to
match, and CLAUDE.md §9 says that no file carries a line every pull request must rewrite.
**What changed in substance:** where two facts are read — the date from the history, the decisions
from the index. Nothing the software does. The gate still fails a state change that did not touch
the status file.
**Recorded in:** [#46](https://github.com/Jersyfi/taktus/pull/46)
