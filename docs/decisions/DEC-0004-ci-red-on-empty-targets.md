# DEC-0004 — CI red on empty targets

**Category:** BLOCKING
**Raised in:** [#1](https://github.com/Jersyfi/taktus/pull/1), as the last section of its description, under the heading "CI status — a direction question"
**Issue:** none; raised before ADR-0017, in the description only
**Needed by:** 2026-09-15

This record is the worked example of the blocking test in ADR-0017 §3. Of the four items in #1
this was the only one that was genuinely blocking, and it was the one presented least
prominently: last, after seventeen rows of README reconciliation and three non-blocking points.
That order is what ADR-0017 §7 fixes.

## 1. What this is about

Every change to this repository passes through a set of automatic checks before it is merged —
the *gates*. They check, among other things, that the code installs, that its types are
consistent, that no part of the core imports a foreign product, and that tests pass. The
repository was set up with all of these before it contained any code. On the main branch the
checks were therefore red: the install step failed because there was no package to install, and
the other checks failed because they pointed at directories that did not exist.

The first pull request with real content — the contracts — could not turn them green, because
turning them green was not what it was about. It asked what to do: merge with the checks red,
add a minimal package so that one more step passes, or mark the checks as not required.

## 2. Why you are being asked

`anchors.md` §1, row O9: *anything that would weaken a gate.* Two of the three options offered
would have weakened one: merging with red checks makes the red signal meaningless for every
later pull request; marking the job as not required removes the gate. The third — a minimal
package — was described by #1 itself as buying one step and blurring the scope. Every option
touched what the gates mean, and that is the owner's call.

## 3. What you must decide

How is the main branch brought to a state where the checks are green and mean something, before
more work is merged on top of red checks?

## 4. What you need to know to decide

- **Gate.** One automatic check that must pass before a change is merged. `make gates` runs all
  of them locally; CI runs the same on every pull request.
- **Empty target.** A gate that points at something that does not exist yet: a test directory
  with no tests, a package with no code, a documentation check with nothing to compare.
- **Why the gates were red.** Not because anything was wrong, but because they found nothing.
  The install step failed on a missing package; the test steps failed because the test runner
  treats "no tests found" as an error; the documentation check called a script that did not exist.
- **The principle at stake.** A gate with nothing to check should report green and say so. A gate
  that is red because it found nothing is broken, not strict — and a red main branch teaches
  everyone to ignore red.
- **Why this was blocking.** Under the blocking test, a decision is blocking if continuing would
  produce work that must be thrown away. Every pull request merged while the checks are red is
  merged unverified; the verification cannot be done afterwards without redoing it. A provisional
  answer — "ignore the red for now" — cannot be marked and cheaply corrected later, because what
  it produces is unverified merges.
- **What the decision commits the project to.** The gates stay in place and stay required. Each
  is made correct on an empty target rather than removed or silenced.

## 5. Options

### Option A — make every gate correct on an empty target (recommended)

- **Meaning:** the package skeleton exists so that install and type checks have something to
  check; the test gates report "no targets yet" and green when they find no tests, and every other
  outcome passes through; the documentation check exists and does something real.
- **Consequence:** the main branch is green for a true reason. From here on, red means something.
- **Effort:** about a day: build configuration, one empty package per component, a small test
  runner wrapper, a documentation check with real rules.
- **Reversibility:** not needed; nothing is weakened.
- **Why recommended:** it is the only option under which the gates keep their meaning and no
  future pull request inherits a red main branch.

### Option B — merge with the checks red, fix them in the next pull request

- **Meaning:** what #1 recommended. The new contracts job is green, the rest stays red.
- **Consequence:** at least one merge under red checks, and a main branch on which "red" cannot be
  distinguished from "broken" until somebody fixes it. Weakens the gate for the duration.
- **Effort:** none now, the same day later.
- **Reversibility:** the red period cannot be undone; what was merged during it stays unverified.

### Option C — mark the failing job as not required

- **Meaning:** the checks still run, but a red result no longer prevents merging.
- **Consequence:** the gate is removed in effect. Turning it back on later is a decision nobody
  remembers to take.
- **Effort:** one setting.
- **Reversibility:** cheap in mechanics, expensive in habit.

## 6. What is blocked

Every merge after #1 until the gates are green: each one either merges unverified or waits.
#1 itself was merged before this was answered, so the answer applies from the next pull request
onward. Without an answer, the main branch stays red and every later pull request repeats the
question.

## 7. How to answer

"DEC-0004: Option A", "DEC-0004: Option B" or "DEC-0004: Option C".

## Outcome

**Decided:** 2026-09-15
**Answer:** Option A. Every gate is made meaningful on an empty target: a gate with nothing to
check reports green and says so; no gate is weakened to make it green.
**Reasoning given:** a gate that is red because it found nothing is broken, not strict. The
package skeleton, the type check, the import contracts, the test gates and the documentation check
are made correct rather than removed. `make gates` must pass end to end on a clean checkout with
no Node installed.
**Recorded in:** [#3](https://github.com/Jersyfi/taktus/pull/3); the principle is stated in
`tools/README.md`
