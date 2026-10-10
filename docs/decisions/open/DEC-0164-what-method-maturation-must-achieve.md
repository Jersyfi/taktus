# DEC-0164 — What method maturation must achieve

**Category:** NON-BLOCKING
**Raised in:** [#220](https://github.com/Jersyfi/taktus/pull/220), for issue #216
**Issue:** [#219](https://github.com/Jersyfi/taktus/issues/219)
**Needed by:** before #217 is built, which observes steps and raises the first proposal
**Provisional answer:** Option A. Issues #217 and #218 are written on it; #216 does not depend on it.

## 1. What this is about

Every step of a process runs on one *method*: a fixed rule, a statistic, a trained model, a
language model, a person, and a few more. A language model can do almost anything, but it is
expensive, and it can answer the same question differently twice. A small trained model — a
*classifier*, which sorts each case into one of a fixed set of classes — is cheap and gives the
same answer every time, but only for a narrow job.

Taktus's promise is that it starts a step on the method that works and later moves it to a
cheaper one when the evidence allows. A language model that has sorted cases into the same six
classes for weeks has produced labelled examples. A classifier trained on them may do the same job
for a fraction of the cost. Taktus is meant to notice that, try it, and propose the move. This is
called *method maturation*. The roadmap's version `0.4.0` is complete when one step has made this
move on Taktus's own proposal, measurably cheaper and reproducible.

What exists: a worker that trains, evaluates and serves classifiers (the ML bench), and — in the
pull request that raises this request — a run that can execute a step on a trained model and hands
an unsure answer to a person. What does not exist is any statement of *when* Taktus may propose a
move, what the proposal must show, and what happens once a person accepts it. The architecture
says the direction; no requirement says the conditions.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: "What a use case requires — what is new beyond
`docs/vision/` and the owner's project definition [...]: its outcome, its verification condition
and its boundary [...]; adding one, changing one, retiring one." Method maturation has no use case,
and the conditions under which Taktus proposes a move are new requirements: the vision and the
definition state the direction, not the conditions.

**Sources checked:** the vision — principle 2 (AI at the core, not only language models), 8
(repeatability and cost control), 10 (the whole autonomy range, with guardrails) and 14 (no
assessment of a person) give the direction and the limit, not a threshold. ADR-0004 says Taktus
measures cost, latency, error rate, corrections and spread per step and "raises change proposals",
and that maturation "needs measurements per step over weeks"; it names no quantity. ADR-0026 and
UC-4.3 say a change of a step's method is always outside the frame — a proposal a person decides,
never a version Taktus makes — which answers who decides, not when to propose.
`docs/architecture/methods.md` §3 gives an example proposal (4,200 cases, six classes, 99.4 %
agreement, about 300 times cheaper), an illustration, not a rule. UC-4.3 and UC-4.4 each exclude
maturation and point to ADR-0004; UC-8.4 places the evaluation of the move in `0.4.0` without
stating it. Both anchor pages: M3.15 places what a use case requires with you, M3.13 places the
choice of a step's method kind with you, which the proposal leaves with you. The register: DEC-0161
chose the bench's library and NTC-0156 what the bench returns; neither states when a move is
proposed.

## 3. What you must decide

Whether method maturation is stated as a use case of its own, with the requirements below.

## 4. What you need to know to decide

- **A case** is one input a step handled, with the result it produced. A **label** is the result
  taken as correct: the language model's answer, or a person's correction of it where a person
  corrected it.
- **Held-out cases** are cases set aside before training and used only to measure the trained
  model. **Agreement** is the share of held-out cases on which the model gives the label.
- **Confidence** is the probability a classifier gives its own answer. A step's **fallback** names
  a threshold: below it, the step does not use the model's answer and hands the case on.
- **Cost per case** is what the step consumed per case, read from what Taktus already records for
  every step.
- The numbers in Option A are proposals for a first version. They are what makes the requirement
  testable. Each is a value you can set differently in your answer.
- **What becomes hard to change:** once proposals are raised and accepted against these conditions,
  loosening them later would mean that models already in use were accepted on weaker evidence than
  the rule then requires. Tightening them is cheap.

## 5. Options

### Option A — a use case of its own, with these requirements (recommended)

- **Meaning:** a new use case, "Taktus proposes a cheaper method for a step", version `0.4.0`,
  filed under `process`, whose requirements are:
  1. **Measured per step, never per person.** For every step, Taktus measures from what it already
     records: cost per case, duration, how often a person corrected the result, and how much
     results spread. The measures belong to the step; none names a person (principle 14).
  2. **A proposal only on evidence.** Taktus proposes to move a step from a language model to a
     trained classifier only when all of this holds: the step's results fall into a fixed set of
     at most 50 classes; there are at least 500 labelled cases and at least 20 in every class; a
     classifier trained by the ML bench on them agrees with the labels on at least 95 % of 20 %
     held-out cases; its measured cost per case is lower than the language model's measured cost
     per case; and training it twice on the same cases gives the same model, byte for byte.
  3. **The proposal is a decision request.** It states the step; the number of cases and the
     classes; the agreement on held-out cases; the cost per case of both methods, measured; the
     exactness class the move would allow; the confidence threshold the new step would fall back
     at; and the model by version and digest. It is raised to whoever owns the process. Asked to
     make the move as a change within the frame, Taktus raises the proposal and makes no new
     version (UC-4.3).
  4. **An accepted proposal is a new version.** The step runs on the trained model, pinned. Below
     the confidence threshold it falls back to the language model it ran on before, so that an
     unsure case is handled as it was. The new version registers only if the model's evaluation
     on the held-out cases is part of it, and it can be rolled back in one act (UC-4.3).
  5. **The move is measured afterwards.** Over the first 100 cases on the new version, Taktus
     reports the cost per case and the share of cases that fell back, beside the old version's.
     A move whose cost per case did not fall is reported as such, with the proposal to roll back.
  - **Not part of it:** neural models and embeddings (#210); a move from a trained model to a
    fixed rule (later); training on anything that describes how a person works; the model hub
    (UC-8.6); applying a move at any autonomy level without a person.
- **Consequence:** the roadmap's completion criterion becomes testable. The work is two issues
  beyond #216: #217 observes steps and raises the proposal, #218 applies an accepted one and measures
  it.
- **Effort:** the use case file, an hour; the two issues, several days of building.
- **Reversibility:** cheap until the first proposal is accepted; afterwards a looser rule means
  re-examining what was accepted.
- **Why recommended:** it states the conditions as numbers a test can hold, it keeps every move
  with a person as ADR-0026 requires, and an unsure case keeps the method that worked.

### Option B — the same requirements as part of UC-4.3

- **Meaning:** UC-4.3, "Taktus changes a process within the frame", gains these requirements as a
  further section, and its boundary no longer excludes maturation.
- **Consequence:** one use case about every change to a process. It mixes changes Taktus makes
  itself with a change it may only propose, which UC-4.3 now keeps apart.
- **Effort:** the same as Option A.
- **Reversibility:** cheap.

### Option C — no use case: the issues state the conditions

- **Meaning:** ADR-0004 and `docs/architecture/methods.md` stay the only statement of maturation.
  The two issues state the conditions they test, and the numbers are the session's.
- **Consequence:** less to write now. The conditions under which Taktus proposes something to a
  person are then set by whoever builds the issue, which is what M3.15 keeps with you.
- **Effort:** none beyond the issues.
- **Reversibility:** cheap now; costly once proposals were accepted on conditions nobody set.

## 6. What is blocked

Nothing waits now. #216, the step on a trained model, depends on no answer here and is built in
the pull request that raises this request. Issues #217 and #218 are written on Option A; the answer is
needed before #217 is built. If no answer arrives by then, #217 is built on Option A, with these
requirements carried by the issue and marked provisional; the use case file is written once you
answer, because adding one is yours. If the answer is Option B or C, the two issues
change their source; if the answer changes a number, the issue's test changes with it.

## 7. How to answer

"DEC-0164: Option A." or "DEC-0164: Option B." or "DEC-0164: Option C." A number changed in
Option A can be written into the answer: "DEC-0164: Option A, with at least 1,000 cases."
