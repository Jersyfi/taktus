# DEC-0014 — Behaviour changes inside an agreed scope

**Category:** NON-BLOCKING
**Raised in:** [#14](https://github.com/Jersyfi/taktus/pull/14), which rebuilds the decision model from your answers
**Issue:** [#15](https://github.com/Jersyfi/taktus/issues/15)
**Needed by:** 2026-10-19
**Provisional answer:** mode 1: decided by the session and stated in the pull request description under "Notes"; the change of #14 is marked there

## 1. What this is about

You answered which questions reach you and which a session decides on its own, and the answers
became four modes with a list of entries each. One kind of choice fits no entry. While building
the removal test, the session changed how a run behaves in one corner: when a step needs an
adapter — a worker, a connector, a model — and none is configured, the run used to stop with an
error thrown out of the engine, leaving the run marked as still running. Now the step ends as
failed with the reason, and the run stops cleanly at that boundary, the way it already did when
no model was configured. Nothing a third party relies on changes; no limit, no autonomy level,
no public statement is touched. But what the software does is different from before, and that
is not naming, ordering, a library, a test or a document.

The four-mode page says what to do with a question that fits no entry: do not decide it alone,
do not escalate it as if it were yours, record it as a question that proposes its mode, and
continue on a provisional answer. This is that question.

## 2. Why you are being asked

No entry of mode 3 or 4 of `docs/decisions/anchors.taktus.md` makes this your call, and no
entry of mode 1 or 2 makes it the session's. The page's own rule for that case — *Neither
list* — says the question is raised as a non-blocking request that proposes which mode it
belongs in, so that the lists grow by use. The nearest entries are M1.2, "ordering of work
inside an agreed scope", and M2.2, "a change of test strategy and what the tests now cover";
neither names a change of behaviour.

## 3. What you must decide

In which mode does a change of what the software does — one that breaks no contract, moves
no limit or autonomy level, and says nothing public — belong when it is made in service of a
scope you have already agreed to?

## 4. What you need to know to decide

- **The four modes.** (1) the session decides, no notice; (2) the session decides and records a
  notice in the register; (3) the session prepares a worked opinion and you decide; (4) you
  decide and the session supplies data. Every entry has an identifier such as M1.2.
- **A notice.** A record in the decision register with what was decided, the evidence, what
  was considered and which entry permits it; nobody approves it, and it stays after the pull
  request is gone. A note in a pull request description does not.
- **An agreed scope.** A milestone's content, or a task you set, such as the one #14 delivers.
  The change in question was needed for the removal test to compare two runs: a run without
  an adapter had to come to a boundary that can be compared.
- **What the options commit you to.** Mode 1 means such changes are visible in pull request
  descriptions and code, and in nothing else afterwards. Mode 2 means every such change leaves
  a record you can search for later, at the cost of one record per change. Mode 3 means you
  read a worked opinion for each, which is the cost this page was rebuilt to avoid for small
  choices.
- **What becomes hard to change afterwards.** Little: an entry can move between modes at any
  time; only the records written under it stay where they are.

## 5. Options

### Option A — Mode 1, stated in the pull request (recommended)

- **Meaning:** a new entry M1.10: "A change of behaviour that breaks no contract, moves no
  limit or autonomy level and says nothing public, made inside an agreed scope; stated under
  *Notes* in the pull request description."
- **Consequence:** such changes cost nothing beyond a sentence; a reviewer sees them in the
  description; nothing accumulates in the register.
- **Effort:** none; the entry is added to the page in the pull request that records your
  answer.
- **Reversibility:** cheap; the entry moves to mode 2 at any time.
- **Why recommended:** the change is of the kind a colleague makes while doing the work you
  asked for, and the description is where a reviewer looks for it; a register entry per such
  change would bury the notices that matter — a weakened gate — among small ones.

### Option B — Mode 2, a notice per change

- **Meaning:** a new entry M2.4 with the same wording, recorded as a notice.
- **Consequence:** every behaviour change outside a contract leaves a searchable record with
  its evidence and the alternatives considered; the register grows by roughly one notice per
  pull request.
- **Effort:** one notice per change, ten minutes each.
- **Reversibility:** cheap; the entry moves to mode 1 at any time and the notices stay.

## 6. What is blocked

Nothing. The change of #14 is stated under *Notes* in its description, as Option A would have
it. If no answer arrives by 2026-10-19, Option A stands and M1.10 is added to the page in the
next pull request that touches it; moving it to mode 2 later costs one edit of the page and no
rework.

## 7. How to answer

"DEC-0014: Option A." or "DEC-0014: Option B." A free-text answer is read back as an
interpretation and confirmed before it is acted on.
