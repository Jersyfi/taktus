# NTC-0176 — A step is measured, and a cheaper method is proposed on evidence

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #217

## 1. What was decided

Until now Taktus measured no step and proposed no change of a step's method. It now does both,
on DEC-0164's provisional answer, Option A, which binds a session that builds issue #217 before
the owner answers (ADR-0084):

1. **Every step is measured from Taktus's own records**: the money per case at the price table,
   the duration, how often a person corrected the result, and how far the results spread. No
   measure names a person.
2. **A person can record what a step's result should have been.** The record is the ledger entry
   `step.corrected`. It changes nothing of the run and nothing outside. It is the label a
   training learns from, and the corrections a step's measure counts.
3. **A step on a language model is a candidate** when its labels fall into at most 50 classes,
   with at least 500 cases and at least 20 in every class, and every case gives the same numbers
   to learn from.
4. **For a candidate, Taktus makes the evidence in two runs of its own.** The ML bench trains a
   classifier twice on four fifths of every class. The model, pinned by its digest, then predicts
   the fifth held out, and one case alone.
5. **A proposal is raised only on evidence**: at least 95 % agreement on the held-out cases, a
   lower cost per case measured at the same price table, and the same model from both
   trainings. It is a decision request to the role `owner`. It is never applied, also when the
   move is asked for as a change within the frame.
6. **A price table may price a second of compute per resource class**, so that a trained
   model's cost can be compared with a language model's. The field is optional; a table without
   it is valid as before.

Which decisions came with it, and why, is ADR-0084: the split drawn by the control plane rather
than by the bench, the cost of a single case rather than of a batch, the role `owner` until a
process names its owner, the threshold 0.9 from `docs/architecture/methods.md` §2.

## 2. The evidence

- DEC-0164, Option A, items 1 to 3, and its section 6: "If no answer arrives by then, #217 is
  built on Option A, with these requirements carried by the issue and marked provisional."
  Issue #217's section "How it is verified" is those items, each a test.
- `tests/components/run/test_maturation.py`: measures read back from a run history the run
  engine wrote, with a correction counted and nobody named; no candidate at 499 cases or with a
  class at 19; no proposal at 94 % agreement or at an equal cost; a proposal that states every
  part DEC-0164 lists, raised once; asked as a change, a proposal and no version.
- `tests/workers/test_maturation_on_the_bench.py`: the same against the ML bench itself, two
  trainings with one digest, the trial on the pinned model, the proposal raised.
- `tests/contract`: the price table's binding and its examples, one with a compute price below
  zero that must fail.

## 3. What was considered

- **Waiting for the owner's answer to DEC-0164.** Rejected: the request itself says #217 is built
  on Option A if no answer has arrived, and every number is a constant that changes with the
  answer.
- **Using the bench's own held-out split.** Rejected: the agreement would be the bench's figure
  about its own model; held out by the control plane, the cases never reach the training.
- **Comparing the two methods in the Takt.** Rejected: its weights are the owner's, M4.3, and
  not decided (DEC-0131).
- **Learning from text values too.** Rejected for now: the bench reads numbers, and text needs
  embeddings, which are #210.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.4.0` item and issue #217, with DEC-0164's provisional answer as its
conditions. The price table gains an optional field; every table valid before stays valid, so no
contract breaks. No limit moves: the training and the trial are held to the budget the command
names. No level moves: nothing is applied, and the move itself stays a person's decision (M3.13).
What maturation must require is the owner's, asked as DEC-0164; nothing here answers it.
