# DEC-0026 — Stacked pull requests and a stored generated list

**Category:** DEFECT
**Raised in:** [#26](https://github.com/Jersyfi/taktus/pull/26), which is repaired by the same change
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

On 2026-09-23 a session opened four pull requests for one task and built each on the branch of
the one before: #23 on `main`, #26 on #23's branch, #39 on #26's branch, #40 on #39's branch.
On 2026-09-27 the owner merged them in that order, which is the order the session had told him
to use. What the host actually did, in seven seconds, by its own timeline:

1. **11:30:17 — #23 merged into `main`**, squashed into one new commit. Its branch was deleted.
2. **11:30:19 — the host moved #26's base to `main`.** #26's branch still carried #23's two
   original commits. They were not ancestors of `main` any more, because squashing had
   replaced them with a new commit of the same content. So `main` and #26 had both changed the
   same lines of `docs/status.md`, `docs/decisions/README.md` and `tools/README.md` since their
   last common commit, and **#26 could not be merged**: the merge command failed, and #26
   stayed open with conflicts. It was never merged, closed or reopened.
3. **11:30:24 — #39 merged into #26's branch**, not into `main`. Its base was #26's branch,
   and merging a pull request merges it into its base.
4. **11:30:26 — #39's branch was deleted, which deleted #40's base, and the host closed #40**
   unmerged.

The result: only #23 was on `main`. #39's content sat inside #26's branch. #40's content — the
target decision, the deployment plan, two needs — was on a closed pull request and nowhere else.

Every conflict was textual. None was two intentions for the same thing: in each hunk, #26's
side was #23's text with #26's further edits on top. Rebasing #26's own commits onto `main`,
leaving out #23's two original commits, applied **with no conflict at all**, and produced a tree
byte-identical to the one the owner's merge of #39 had produced. Nothing had to be chosen.

A second fault made the first one certain. `docs/status.md` stored a generated list — the open
needs and decisions — which every pull request touching the register rewrote. Any two such pull
requests conflict on it, stacked or not, and whichever merges first leaves the other's copy
stale. All four pull requests touched it.

## 2. Why you are being asked

You are not. The repository told sessions to squash-merge (CLAUDE.md §9) and said nothing
against stacking, which squash-merging breaks; and it stored a generated list in a file every
pull request edits by hand, which CLAUDE.md §9 says generated output must not be. It contradicted
itself, which is entry M1.4 of `docs/decisions/anchors.taktus.md`. How the work is organised is
mode 1; you said so when you asked for the fix.

## 3. What you must decide

Nothing. The fix is in the same pull request as the repair, and the record keeps the reasoning
findable for the next time four changes belong together.

## 4. What you need to know to decide

- **The cause was stacking, not the generated file.** `tools/README.md` conflicted too, and it
  is written by hand. Even with no generated file anywhere, stacking plus squash merge plus
  branch deletion would have produced the same three outcomes: a conflicting #26, #39 in the
  wrong branch, #40 closed.
- **Squash merging is kept.** It is what gives `main` one commit per change with a
  Conventional Commits title, and it is in CLAUDE.md §9. It is only incompatible with stacking.
- **A generated list in a file is a copy.** Its source is the register. The copy is useful to a
  reader and dangerous to a merge. A pull request description is also a copy — but it belongs
  to one branch, is written from that branch, and is never merged with anything.
- **The anchor tables and the register's index are not generated.** The conflict between #16
  and #22 on the mode-2 table of `anchors.taktus.md` was two intentions meeting: #16 added a
  column, #22 added a row written against the table without it, and the merge had to give the
  new row its cell. That cannot be generated away. It is resolved by rebasing on `main` and
  merging by hand, which the first rule below makes the normal path. The same holds for the
  index of `docs/decisions/README.md`: its outcome column is a sentence someone writes.

## 5. Options

None for the owner. Three were weighed, and the choice is recorded here because you named them:

- **Generate `docs/status.md` on `main` at merge time**, by a workflow that commits the result.
  Rejected: CI in this repository validates and never writes (`.github/workflows/ci.yml`, first
  line); a commit pushed by the workflow's own token starts no CI of its own, so the regenerated
  file would reach `main` unchecked; and every branch would still carry a copy for the gate to
  compare, which is the conflict again.
- **Have the gate regenerate and compare, instead of requiring an edit.** It already compared;
  the edit was what `make generate` wrote into the file, and that edit was the conflict.
  Regenerating in the gate alone changes nothing about what is committed.
- **Store no generated list at all** — chosen. The list is printed by `make status`, carried as
  the last section of every pull request description where CI checks it against that branch's
  register, and live in the issue tracker under the labels `needs-owner` and `decision-request`.
  Section 3 of the file says where those are, and the gate fails a section 3 that stores a list.

And, first, because it is the cause:

- **Every pull request targets `main`.** A change that needs an unmerged change waits for it,
  then rebases on `main`. CI fails a pull request whose base is any other branch. CLAUDE.md §9
  says so, and the pull request template.

Also removed: the header line of `docs/status.md` that listed the pull requests accounting for
the file. Every pull request rewrote it, it was checked by nothing, and the commit history says
the same thing without conflicting.

## 6. What is blocked

Nothing. #26 now carries its own four findings, the report you merged as #39, the target and
the plan that were #40, and this fix, rebased on `main`, green.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0026" in an issue, with the reading you hold.

## Outcome

**Corrected:** 2026-09-29
**What was wrong:** the repository squash-merged pull requests and did not forbid building one
on another's branch, so a stack of four merged in order produced a conflicting #26, merged #39
into #26's branch instead of `main`, and closed #40 unmerged when its base branch was deleted;
and `docs/status.md` stored a generated list that every pull request touching the register
rewrote, so any two of them conflicted on it.
**Why it was wrong:** squash merging discards a branch's commits. A pull request built on those
commits then carries history that is on `main` in content but not in ancestry, and conflicts
with its own foundation. A generated copy in a hand-edited file is a conflict between every pair
of pull requests that change its source, and is stale from the moment either merges.
**What it now says:** every pull request targets `main`, and CI fails one that does not; a
dependent change waits and rebases. `docs/status.md` section 3 says where the list is and stores
none; `make status` prints it; the pull request description carries it and CI checks it there.
The status file has no per-pull-request header line. ADR-0028 §3 is amended to match, with the
cost stated: a reader of the file alone sees where the list is, not the list.
**What changed in substance:** how pull requests are organised and where one generated list
lives. Nothing the software does. The gate still fails a status file that a state change did not
touch, and still checks the pull request description against the register.
**Recorded in:** [#26](https://github.com/Jersyfi/taktus/pull/26)
