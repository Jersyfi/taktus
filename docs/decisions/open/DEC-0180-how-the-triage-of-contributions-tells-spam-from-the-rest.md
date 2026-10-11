# DEC-0180 — How the triage of contributions tells spam from the rest

**Category:** NON-BLOCKING
**Mode entry:** M3.13
**Raised in:** [#263](https://github.com/Jersyfi/taktus/pull/263), which builds issue #245 for UC-1.9
**Issue:** [#260](https://github.com/Jersyfi/taktus/issues/260)
**Needed by:** before the triage is switched on for this repository
**Provisional answer:** Option A. `blueprints/dev-orchestration/processes/P-05-triage.yaml` screens with fixed patterns first and asks a language model only where none matched; a person classifies where the model's answer fails its check.

## 1. What this is about

People Taktus does not know open issues and pull requests in this public repository. Since
DEC-0175, each one starts a process that classifies it for you: a defect, a feature with the
version it would belong to, or spam (UC-1.9). Spam is closed without asking you. A defect or a
feature is put to you as a decision request.

Building it, the session had to choose how the classifying is done. There are two steps.

- **The screen.** A fixed list of patterns is searched in the title and the text: gambling,
  drugs sold online, money offers, a text that is mostly links. A match is spam. The same text
  gets the same verdict every time.
- **The judgement.** Where no pattern matched, a language model reads the contribution and
  answers three lines: the class, the planned version, one sentence of summary. A rule then
  checks the answer: one of the three classes, one of the roadmap's versions, a summary. An
  answer that fails the check goes to a person.

What was attempted: both steps run end to end against the fake repository service and a fake
model, in `tests/integration/test_triage.py`. The model's spam verdict closes a contribution
without asking anyone, as the use case requires.

## 2. Why you are being asked

Entry M3.13 of `docs/decisions/anchors.taktus.md`: "Choosing the method kind of a step — `rule`, `statistics`, `ml`, `neural`, `llm`, `worker`,
`human`, `wait` — where the step's exactness class admits more than one kind." Both steps admit more than one:
the screen could be left to the model, and the judgement could be a rule or a person.

**Sources checked:** the vision (`docs/vision/`) — principle 8, repeatability and cost
control, and CLAUDE.md §3 prefer the more reproducible method where it does the job, which
points to the screen; they do not say
that a model may close something without a person. UC-1.9 §2 requires spam closed without a
person, and a class for every contribution; it names no method. The blueprint's description of
P-05 names a language model for the classification and expects it to mature to a trained model
(`blueprint.yaml`). DEC-0080 is the precedent: the owner chose a rule for P-01 where a rule does
the job. The ADRs: ADR-0004 asks for a method, a reason and a fallback per step, ADR-0014 and ADR-0018
bound which methods an `exact` step admits, ADR-0088 builds the triage; none chooses a
method for a `tolerant` judgement. The anchor pages: both place the choice with you (M3.13).
None of them chooses here.

## 3. What you must decide

Which method tells spam from the rest, and which classifies the rest.

## 4. What you need to know to decide

- **A pattern** catches only the spam it names. Spam that is not on the list goes on to the
  model. A pattern never closes a real contribution unless its words are on the list.
- **A model** reads anything, and can be wrong both ways. A wrong spam verdict closes a real
  contribution; a maintainer reopens it with one click, and the closing comment says so. A
  contribution written to steer the model can make it answer one of three classes and a
  planned version, nothing else: the check refuses any other answer, and nothing in the process
  merges, blocks or acts as anyone.
- **Cost.** One short model call per contribution not caught by a pattern.
- **A person** for everything would mean no automatic spam closing, which UC-1.9 requires.

## 5. Options

### Option A — patterns first, the model for the rest, a person where the answer fails (recommended)

- **Meaning:** as built. The screen is a rule (`exact`), the judgement a language model
  (`tolerant`), its fallback a person.
- **Consequence:** spam on the list never reaches a model; the rest costs one call each.
- **Effort:** none; it is built.
- **Reversibility:** cheap: the methods are lines in the bundle.
- **Why recommended:** the reproducible method does what it can, and the model only what needs
  judgement — the order CLAUDE.md §3 asks for.

### Option B — the model for everything

- **Meaning:** no screen; the model classifies every contribution.
- **Consequence:** simpler; every spam costs a call, and every verdict can vary between runs.
- **Effort:** an hour.
- **Reversibility:** cheap.

### Option C — patterns only, a person for the rest

- **Meaning:** no model. What no pattern catches is classified by you, as part of the decision
  request.
- **Consequence:** fully reproducible; you classify every contribution that is not obvious
  spam, and a defect or feature arrives without a proposed version.
- **Effort:** a day: the request would carry a classification form.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. The pull request builds on Option A, marked provisional in the bundle. On Option B the
screen step is removed; on Option C the model step is. Either is one change of its own.

## 7. How to answer

"DEC-0180: Option A.", "DEC-0180: Option B." or "DEC-0180: Option C." — in issue
[#260](https://github.com/Jersyfi/taktus/issues/260). A free-text answer is read back as an interpretation and confirmed before it is acted
on.
