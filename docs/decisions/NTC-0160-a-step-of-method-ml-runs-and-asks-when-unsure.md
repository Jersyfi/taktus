# NTC-0160 — A step of method ml runs, and asks when unsure

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** [#220](https://github.com/Jersyfi/taktus/pull/220), for issue #216

## 1. What was decided

Until now Taktus refused, before a run started, every step whose method is `ml`: a trained model,
which gives the same answer every time at a pinned version. Such a step now runs. Four things
about how it runs were not fixed by any document, and were decided here (ADR-0076):

1. **It runs on a worker that offers `ml.predict`**, such as the ML bench. The step names its
   rows and its model file with the digest of its bytes; Taktus turns them into a prediction and
   hands it over like any other work for a worker.
2. **The step's confidence is the lowest confidence of its rows.** If one row is unsure, the
   step is unsure.
3. **The step's fallback condition must read `confidence < t` or `confidence <= t`.** Taktus
   compares the number; nothing else is evaluated. A step without a fallback, or with a fallback
   in another form, is refused before the run starts.
4. **An unsure step goes to a person, and its answer stays in the step.** The step waits for a
   person, who performs it and reports it performed, at any autonomy level. The steps after it
   receive nothing from the model. A fallback to another method is refused before the run
   starts in this version.

The roadmap item "method maturation with change proposals" was split into three issues, #216 to
#218, and named in `docs/roadmap.md` (M1.7). What maturation must require is the owner's,
asked as DEC-0164.

## 2. The evidence

- `docs/architecture/methods.md` §2: "A model that is unsure does not guess — it asks", with
  `fallback: when: confidence < 0.9, to: human`. The four points are what that sentence needs
  of a run.
- ADR-0004: "Training runs as a worker for isolation and resource reasons." The control plane
  predicts nothing itself, so no library for machine learning enters it (ADR-0003).
- NTC-0156: the bench accepts a model only with its digest, and returns every row's class with
  its confidence. The step uses exactly that.
- `tests/components/run/test_ml_steps.py`: a sure prediction becomes the step's result, naming
  the model and every row; an unsure one waits for a person and reaches no later step, neither
  as a result nor as an artifact; every refusal happens before the run starts.
  `tests/workers/test_ml_steps_on_the_bench.py`: the same against the ML bench itself, with the
  same result digest twice for the same model and rows.

## 3. What was considered

- **The mean confidence of the rows.** Rejected: one unsure row would hide behind many sure ones,
  and the step would pass on an answer the model did not stand behind.
- **A fallback per row.** Rejected for now: a person would complete a result row by row, which
  the run cannot take as an answer yet. It is named as the boundary of #216.
- **Letting a person confirm the model's answer instead of performing the step.** Rejected:
  confirming would pass on what the model was unsure of, under a person's name.
- **A new ledger kind for a fallback.** Rejected: `step.awaiting` already says the step waits for
  a person, and its outcome `fell_back` says why; a new kind would change the changes contract.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.4.0` item, issue #216. The step contract is unchanged: `ml` already
requires a pinned model, and a fallback is already allowed on any step. No limit moves, and no
level: an `ml` step is held at its level like any step on a worker. Which method a step runs on
stays a choice of whoever writes the process (M3.13); nothing here chooses one.
