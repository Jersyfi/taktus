# ADR-0141 — Maturation reads a step's score on the evaluation cases, and a move that scores lower is proposed for rolling back

**Status:** accepted · extends ADR-0084 (a step measured, a move proposed on evidence), ADR-0114 §5 (a move measured over its first cases) and ADR-0134 (evaluation cases and their scores) · issue #408

## Context

Issue #408 asks that the results of a process's evaluation cases feed maturation's evidence.
Maturation (ADR-0084) proposes moving a step from a language model to a trained model. Its
evidence is the step's own cases. A trained model must agree with their labels on held-out
cases, cost less, and give the same model twice. After a move, the moved step is measured over
its first 100 cases, by cost alone (ADR-0114 §5).

That evidence has one blind spot. The labels are mostly the language model's own answers. A
trained model that agrees with them agrees with their mistakes too (ADR-0084, where the promise
ends). A move can therefore be cheaper and worse at once, and nothing would show it.

The evaluation cases close part of that gap. A case carries a **target**: the result a person
says a step should produce (ADR-0134 §1). A **scorer** holds a step's result to it and gives a
**score** from 0 to 1. A scored evaluation names the score of every step its scorers score, on
each version it ran.

## Decision

### 1. A step's score on the cases is read by rule

A step is **scored** where a scorer of its version scores it. Its **score** is read from the
newest scored evaluation that ran the version and gave the step a score. That is a drift
evaluation, or the active side of a change; both run the version as it is registered. The
score is the mean of every score the step's scorers gave over the cases run
(`process/domain/service/scoring.step_score`). A case a judge left to a person has no score, and
the step then has none in that evaluation.

The score names the version, the step, the evaluation and how many cases it ran. It also says
whether the version's cases run on a schedule, which means a score will come without a change.
It is a score of the step. It never names a person (principle 14).

The run component reads it through the port `EvaluationScores` (`run/ports/scores.py`), with the
tenant's tolerance (ADR-0134 §8). The composition root answers from the process component's
versions and evaluations (`composition/maturation.RepositoryScores`), because components never
import each other.

### 2. A proposal names the language model's score

A proposal to move a step (ADR-0084 §6) names the step's score on the cases, where the step is
scored. The person who decides then reads what the language model achieves against targets a
person set, beside the agreement with labels it mostly set itself. The score is not a condition
of the proposal. The trained model has not run on the cases yet, so there is nothing to compare
it with.

### 3. A move is held to the score it replaced

A move's review (ADR-0114 §5) reads the step's score in the moved version and in the version it
replaced. The verdict is a rule, taken in this order:

| Order | Condition | Verdict |
|---|---|---|
| 1 | fewer than 100 cases ran on the moved version | `measuring` |
| 2 | the replaced version has a score, the moved one none yet, and its cases run on a schedule | `measuring` |
| 3 | the moved version's score is below the replaced one's by more than the tolerance | `worse` |
| 4 | otherwise, by the cost per case | `cheaper`, `not_cheaper` or `unpriced` |

A move that is `worse` is reported as one that is `not_cheaper` is: with a proposal to roll it
back, a decision request to the role `owner`. Its situation states both scores, their
evaluations and the tolerance. A rule never rolls back on its own (UC-4.3 §2). The verdict is
recorded once, as `method.measured`, with the scores in the measures.

A worse score outranks a lower cost. A cheaper step that reaches its targets less often is the
regression ADR-0134 §4 blocks for any change made through a proposal. A move is registered
without a proposal (ADR-0114 §2), so this is where it is held to the same comparison.

### 4. Method and exactness

| Part | Method | Exactness | Reason | Rejected |
|---|---|---|---|---|
| the step's score | `rule` | inherits the scorer's | a mean of recorded scores, which a person can recompute | `statistics` — a test of significance needs more cases than a process carries |
| the move's verdict | `rule` | `exact` | a proposal to roll back must follow from the recorded scores, the tolerance and the costs every time (ADR-0023) | `llm` — a decision that proposes a rollback is never probabilistic |

## Alternatives

- **Scoring the trained model on the cases before the proposal.** It would compare the two
  methods before anything moves. The trial would need each case's numbers as the step's prompt
  was rendered from them. A case is a set of inputs, and its numbers exist only once a run has
  resolved them. That is a new trial for every candidate, and its cost grows with the set.
- **The score as a condition of the proposal.** A language model with a low score would then
  never be proposed for a move, even where the trained model would do better.
- **Recording the review, then a later score separately.** Two verdicts for one move would
  disagree in the record. Waiting for the score keeps one verdict, recorded once.
- **Every scored evaluation, averaged.** An old evaluation would weigh as much as the newest.
  The newest is the one a person last saw, as drift compares (ADR-0134 §4).

## Consequences

- `run`: `maturation.StepScore`, `maturation.worse`, the verdict `worse`; `MoveReview.score`,
  `replaced_score` and `tolerance`; `Proposal.score`; the port `EvaluationScores`. Both
  `ProposeMovesHandler` and `ReviewMovesHandler` take it, optionally.
- `process`: `scoring.step_score` and `scoring.comparison`.
- `composition`: `RepositoryScores`, wired into maturation by the daemon and by `taktusctl`.
- No migration: scores are read from the evaluations already kept, and the review's document
  carries them.

## Where this promise ends

A score is only as good as its scorer and its cases (ADR-0134, where the promise ends). A step no
scorer scores is measured by cost alone, as before. A process whose version declares no
schedule is evaluated only when a later change runs it as the active side. Its moved version may
therefore be reviewed by cost before any score of it exists. The move is then recorded without
one, and a later score changes nothing about the recorded verdict.

The trained model is not scored on the cases before it is proposed. Its score is first known
after the move, once an evaluation runs the moved version. Until then a worse move runs in
production. The review compares the newest scores of two versions, which may come from
evaluations of different dates and different sets of confirmed cases. A score that falls by
less than the tolerance is not seen. Nothing here proposes a move because of a score, and
nothing is rolled back without a person.
