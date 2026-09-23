# DEC-0019 — The model for the purpose `reasoning`

**Category:** NON-BLOCKING
**Raised in:** [#23](https://github.com/Jersyfi/taktus/pull/23), which wires the three credentials and raises their renewals
**Issue:** none; the owner gave the answer with the commission, and the record carries it

## 1. What this is about

Process P-02 Refinement has one step that judges: `refine`, method `llm`, purpose `reasoning`.
It reads an issue and its comments and writes the acceptance criteria as a Markdown section.
Every other step of P-02 and every step of P-03 but one is a rule; the coding worker's own
model is the worker's business and not this question.

A purpose is not a model. The bundle names `reasoning`; the deployment decides which endpoint
and which model serve that purpose (`TAKTUS_MODEL_ENDPOINT`, `TAKTUS_MODEL_NAME`), and the
ledger records which model answered. NEED-0003 offered the current default model as the
example line to put in `.env`. That was an example, not a choice, and the choice is the
owner's: entry M3.12 binds a model purpose to a provider and M3.14 routes between approved
models.

## 2. Why you are being asked

Because both entries are mode 3 (`docs/decisions/anchors.taktus.md`), and because the question
is not really about a model name. It is method selection (ADR-0004) applied one level down:
the bundle chose `llm` over `rule` and `ml` with its reason, and the same discipline then asks
which model within that method does the job most cheaply. Guiding principle 8 is repeatability
and cost control; a step that uses the largest model available because it was the example in a
document is a step nobody chose.

## 3. What you must decide

Which model answers the purpose `reasoning` for this tenant, and on what grounds the choice
is revisited.

## 4. What you need to know to decide

- **What the step asks of a model.** Read an issue of a few hundred words and its comments,
  and produce a section headed exactly `## Acceptance criteria` with three to eight checklist
  items, each one testable sentence. The system message states the format; the step's own
  check enforces it (`pattern`), and an answer that fails the check does not leave the step —
  the step fails and the run escalates to a person (`fallback: human`). Nothing downstream
  trusts the model: P-03 reads the section a person has had the chance to edit.
- **What it costs.** `max_output_tokens` is 1024; the input is the issue and its comments. It
  is one request per run. The difference between the models is a factor, not an order of
  magnitude in absolute money at this volume — and the volume is the point: at one issue a day
  it is loose change, at the rate `0.2.0` aims for it is the first line of the budget
  ADR-0005 designs.
- **What a wrong answer costs.** Nothing silently: the check refuses a malformed answer, and a
  poorly judged criterion is read by a person on a public issue before P-03 acts on it. This
  is the cheap end of the risk scale, which is exactly where a smaller model belongs.
- **The exactness class is `sourced`, not `exact`.** Every method is permitted to produce it
  as long as the result names its source and passes its check (ADR-0014, ADR-0018). The class
  does not decide this question; it only says that the question is allowed to be asked.
- **Where the answer lives.** In `.env` of the deployment, never in the repository:
  `TAKTUS_MODEL_NAME` is one deployment's choice, and `.env.example` carries the name of the
  variable and no value. This record is therefore the only place in the repository that says
  what this tenant chose and why.

## 5. Options

### Option A — the smaller model of the same family (recommended)

The cheapest model that does the job, on the same endpoint and the same key as the coding
agent's (NEED-0003 §4). One workspace, one spend limit, one bill. Writing a checklist from a
well-written issue is a formatting-and-judgement task at the low end of what a model is asked
for, the answer is checked before it leaves the step, and a person reads it on a public issue
before anything builds on it. If the criteria turn out thin, the evidence is visible in the
comments and the line is one line to change.

### Option B — the largest model of the same family

The example line of NEED-0003. Better judgement on a badly written issue, several times the
cost per run, for an output a person reads anyway. It buys quality where quality is already
fenced by a check and a human reader, and it sets the wrong default for every later `llm`
step: the model chosen when nobody chose.

### Option C — a local model server

Costs nothing per token and keeps the issue's text on the owner's machine. The issues of this
repository are public, so there is nothing to keep; and a local server is one more thing that
must be running before `tools/first_run.sh` does anything, on the day the first run finally
has its credentials. Worth revisiting for sovereignty (guiding principle 11) when the
deployment stands, not on the way to the first run.

## 6. What is blocked

Nothing. The first live run needs a model name in `.env`, and this record says which one it
is and why.

## 7. How to answer

Name the option in this record, or say "Option A" in issue #20 before it is closed. To change
it later: one line in `.env`, and an amendment here saying what the runs showed.

## Outcome

**Decided:** 2026-09-23
**Answer:** Option A. The purpose `reasoning` is served by the smaller model of the family the
coding agent uses, on the endpoint and key of NEED-0003. `TAKTUS_MODEL_NAME` in this tenant's
`.env` names it; the repository holds the name of the variable and not the name of the model.
**Reasoning given:** the cheapest model that does the job. The choice of method does not stop
at `llm`: within a method the same question is asked again, and here the job is bounded by a
format the system message states, a check the step enforces, and a person who reads the result
on a public issue before P-03 acts on it. The larger model would buy judgement where judgement
is already fenced, and would make "the biggest available" the default for every later step.
The decision is revisited on evidence: a criterion a person had to rewrite is the evidence
that the job is harder than this model does, and the first run's report
(`docs/runs/first-run.md`) records the criteria the model produced and what they cost, so that
there is something to revisit against.
**Recorded in:** [#23](https://github.com/Jersyfi/taktus/pull/23)
