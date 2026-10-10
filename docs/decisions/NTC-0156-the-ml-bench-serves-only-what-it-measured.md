# NTC-0156 — The ML bench serves only what it measured

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** [#215](https://github.com/Jersyfi/taktus/pull/215), for issue #89

## 1. What was decided

Taktus has a new worker, the ML bench (`workers/mlbench/`), which trains, evaluates and predicts
with classical models. Four things about what it hands back were not fixed by any document, and
were decided here:

1. **A model is a file of numbers.** The bench writes a trained model as JSON: its features, its
   classes, the scaling of its inputs, its weights, the seed, the digest of the dataset, the
   versions of the worker and its libraries, and its metrics. Loading it runs no code. A model is
   never handed over as a serialised program object.
2. **What is served is what was evaluated.** The metrics of a training are computed by the same
   function that serves predictions, over the model file as written — never by the classifier in
   memory.
3. **A model is used only as pinned.** An evaluation or a prediction names its model with the
   digest of its bytes. A model without a digest is rejected; one whose bytes do not match is used
   for nothing.
4. **A prediction carries its confidence.** Every row's class comes with its probability, so that
   a step's fallback can send an unsure answer to a person.

The issue was split as well: the classical part on an ordinary processor is #89, embeddings and
the training run on an accelerator are #210 (M1.7).

## 2. The evidence

- `docs/architecture/methods.md` §1: `ml` is reproducible "exactly, at a pinned model version";
  §2: "A model that is unsure does not guess — it asks", with `fallback: when: confidence < 0.9`.
  A pinned model and a confidence per answer are what those two sentences need of a worker.
- ADR-0004: a trained model enters the model hub "with version, owner, purpose and evaluation
  history"; the file carries its evaluation and its origin.
- ADR-0021: every result carries what produced it, from which inputs; the file names the dataset
  by digest and the worker and libraries by version.
- `tests/workers/test_mlbench.py`: the same dataset, seed and version give the same digest; a
  training stopped and resumed gives the digest of one run straight through; the file predicts
  exactly the classes, and the probabilities to nine places, that the classifier predicted, for
  two classes and for three; a mismatched digest is rejected in the task and fails the load behind
  a URI, producing nothing.

## 3. What was considered

- **The library's own serialised model as the artifact.** Rejected: loading it runs code, so a
  model artifact from anywhere would be a program run by the bench, and its bytes depend on the
  library's internals rather than on the numbers.
- **Metrics from the classifier in memory.** Rejected: a file that predicts differently from the
  object it was written from would leave the bench with metrics that are not its own.
- **Accepting a model without a digest.** Rejected: a step on method `ml` must name its model at a
  version (`contracts/shared/v1/Step.json`); a worker that accepts an unpinned one could serve a
  step with something nobody can name.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is the roadmap's `0.4.0` item for the bench, issue #89. The worker contract is unchanged:
the shape of a task's inputs belongs to the task (`contracts/worker/v1`, `Task.inputs`). The
library the bench uses is not decided here; it is DEC-0161 (M3.8).
