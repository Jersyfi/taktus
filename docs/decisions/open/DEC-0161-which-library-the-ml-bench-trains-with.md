# DEC-0161 — Which library the ML bench trains with

**Category:** NON-BLOCKING
**Raised in:** [#215](https://github.com/Jersyfi/taktus/pull/215), for issue #89
**Issue:** [#212](https://github.com/Jersyfi/taktus/issues/212)
**Needed by:** before #210 is built, which adds the bench's second family of models
**Provisional answer:** Option A, built in `workers/mlbench/` and named in its README.

## 1. What this is about

Taktus can now train its own small models. When a step of a process has run on a language model
long enough, the answers it gave are labelled data. A small model trained on them does the same
work more cheaply, and gives the same answer every time. The worker that trains such a model is
called the ML bench. It is built in the pull request that raises this request.

The bench needs a library that does the arithmetic of training: fitting a model, splitting data,
measuring how often the model is right. Writing that arithmetic ourselves is possible for one kind
of model and costly for every further kind. Established libraries exist for it.

The bench ships with every Taktus release, as one of its reference workers. So the library becomes
part of what every installation of Taktus runs.

## 2. Why you are being asked

Entry M3.8 of `docs/decisions/anchors.taktus.md`: "A new dependency at integration-code tier 1 —
what Taktus itself needs in order to run: database, queue, secret store, telemetry, reference
workers". The ML bench is a reference worker (`docs/architecture/contracts.md` §4), and the library
is what it needs in order to run.

**Sources checked:** the vision — principle 3 (model-agnostic) and principle 13 (freedom instead of
lock-in) require an open library and say nothing about which; the non-goals forbid training
foundation models and allow task-specific ones. ADR-0004 says training runs as a worker and names
no library. ADR-0007 asks for the training proof case and names no library. The integration-code
rules (`docs/architecture/contracts.md` §7) give the conditions a tier-1 dependency must meet — an
open contract, an OSI licence, self-hostable, exportable data, an active community — and each
option below is held to them; they do not choose between two that meet them. Both anchor pages
place the choice with you (M3.8). The register holds one precedent of the entry, DEC-0032, the
database, which does not decide this one.

## 3. What you must decide

Which library the ML bench trains, evaluates and predicts with.

## 4. What you need to know to decide

- **Classical models** are the ones the method table of Taktus calls `ml`: classification,
  regression, anomaly detection, ranking. They are small, train in minutes on an ordinary
  processor, and give the same result every time from the same data and the same seed.
- **What the bench does with the library today:** it trains one kind of model — a linear
  classifier, which weighs each input and adds the weights up — one pass over the data per step,
  measures it on rows it held back, and writes the model as a plain file of numbers. Predicting
  from that file uses only the numbers, not the library's own model object, so a model file stays
  readable whichever library made it.
- **What is hard to change afterwards:** the further kinds of model the bench learns will be built
  on the library chosen. The model files themselves are not tied to it.
- **Where the library is never present:** in the control plane, the part of Taktus that plans and
  runs processes. Only the bench's own image carries it.
- **The libraries' terms.** scikit-learn is under the BSD licence, maintained by a large community
  since 2007, and runs on NumPy and SciPy, also BSD. All three are open source and run on your own
  machines; none calls out to a vendor.

## 5. Options

### Option A — scikit-learn, with NumPy (recommended)

- **Meaning:** the bench trains with scikit-learn 1.9.1 and NumPy 2.5.4, each pinned to one exact
  version in the bench's image and in the tests. Their own dependencies — SciPy, joblib,
  threadpoolctl, narwhals, cloudpickle — are pinned the same way.
- **Consequence:** every classical kind of model the method table names is one function away; the
  image of the bench grows by about 370 MB, uncompressed. A new version of the libraries is a change that the
  bench's reproducibility test must pass, like any other.
- **Effort:** none beyond what is built.
- **Reversibility:** cheap now — one worker, one kind of model — and costlier with every kind
  added.
- **Why recommended:** it meets every condition a tier-1 dependency must meet, it is the reference
  library for exactly these models, and it saves writing and proving the arithmetic of each kind
  ourselves.

### Option B — NumPy only, the training written in Taktus

- **Meaning:** the bench keeps NumPy for arrays and implements each kind of model itself.
- **Consequence:** fewer and smaller dependencies; every further kind of model is code of our own
  to write, test and keep correct. The linear classifier would be rewritten now.
- **Effort:** about a day for the linear classifier; days for each further kind.
- **Reversibility:** cheap.

### Option C — a deep-learning framework

- **Meaning:** the bench trains with a framework built for neural networks, which can also fit
  linear models.
- **Consequence:** one library for classical models and for the embeddings that #210 adds; an
  image of several gigabytes for work that needs none of it, and a far larger surface to pin.
- **Effort:** about a day to rewrite what is built.
- **Reversibility:** costly once #210 builds on it.

## 6. What is blocked

Nothing waits. The bench is built on Option A and is marked as provisional in its README. If the
answer is Option B, the linear classifier is rewritten in about a day and the tests stay as they
are. If it is Option C, the same, and #210 is built on it. The answer is needed before #210 is
built, because that task adds the bench's second family of models and with it a second library.

## 7. How to answer

"DEC-0161: Option A." or "DEC-0161: Option B." or "DEC-0161: Option C."
