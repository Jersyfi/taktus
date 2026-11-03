# ADR-0183 — Text becomes numbers through a neural encoder the bench trains and pins

**Status:** accepted · extends ADR-0007, ADR-0076, ADR-0084 and ADR-0114 · issues #210 and #218,
roadmap `0.4.0` ("training, evaluation, embeddings, classical ML") · DEC-0161 (the bench's
libraries), DEC-0226 (the accelerator is a tenant's)

## Context

The ML bench trains, evaluates and serves a linear classifier on numbers (ADR-0007, #89). Every
step of a process Taktus runs for itself that runs on a language model reads text: an issue's
title, a message, a pull request's description. Method maturation (ADR-0084) learns only from
the numbers a step's prompt was rendered from, so none of those steps can be a candidate, and the
roadmap's `0.4.0` criterion — a step moved from a language model to a trained model on Taktus's
own proposal — cannot be met on Taktus's own instance (ADR-0114, *Where this promise ends*).

`docs/architecture/methods.md` §1 names embeddings under the method kind `neural`: reproducible
exactly, at a pinned version and seed. Issue #210 asks the bench to produce them. Its second
half, a training that holds an accelerator for hours, is proven at a tenant that has one
(DEC-0226); the project proves the bench on an ordinary processor.

Three constraints bound the choice. The bench's libraries are scikit-learn and NumPy (DEC-0161),
and a model file is data, never code. Foundation models are a non-goal
(`docs/vision/non-goals.md`). A model must give the same bytes from the same inputs, seed and
version, because a step on it is pinned by digest (ADR-0076).

## Decision

### 1. The encoder

A text is lower-cased and its white space folded. Its character n-grams of two to four
characters are counted into 512 buckets. The bucket of an n-gram is a stable hash of its bytes
(BLAKE2b), never a hash that changes between processes. The counts are scaled to length one.

The encoder is a neural network of one layer: 512 inputs, 32 units with the tanh activation. It
is trained as an autoencoder — the 32 units must let a linear layer rebuild the 512 counts — by
800 passes of full-batch gradient descent at a fixed step size, from weights drawn from the
task's seed. Its weights are rounded to eight decimal places. A text's embedding is the encoder's
32 units. An encoder whose error is not finite is refused, never written.

The encoder is a document of numbers: the bucket count, the n-gram lengths, the width, the seed,
the number of passes, the rows it learned from, its final error and its weights. It names the
worker's version and its libraries' versions, as a model file does.

### 2. Two ways the bench uses it

- **`embed`** — an operation of its own. The task names the text columns under `inputs.text`.
  The bench trains one encoder per column on every row, and returns the vectors as a dataset
  artifact (`embeddings`) and the encoders as a model artifact (`embedder`). The tool is
  `ml.embed`.
- **`train` with `inputs.text`** — the named columns are embedded before the classifier sees
  them. Each column's encoder is trained on the training split alone, so the held-out rows stay
  unseen. The 32 columns of an embedding are named `<column>#1` to `<column>#32` and follow the
  numeric features. The model file carries every encoder under `text`. `evaluate` and `predict`
  read a model's text columns from the file and embed them with the file's own encoder, so that
  what is served is what was evaluated.

The worker's version becomes `0.2.0`.

### 3. Maturation reads text

A value a step's prompt was rendered from that is a non-empty string is a **text** of the case,
named by its dotted path, as a number is a feature. A case's texts and numbers are both what a
training learns from. A step is a candidate when every case gives the same numbers and the same
texts, and at least one of either. Every other floor of UC-4.24 stays as it is. The training's
dataset carries the texts as columns after the numbers, and the training task names them under
`inputs.text`. The trial predicts the held-out cases with their texts, through the model file.
A proposal names the texts the model reads.

A value that is neither a number nor a text — a truth value, an empty string — is named in the
proposal and not learned from, as before.

### 4. The moved step predicts its one case with its text

A moved step's work names its texts beside its features: `dataset: {values, features, texts}`.
The run renders the case as one CSV row, the numbers and then the texts, and the worker embeds
the texts with the encoder of the pinned model file. A case without one of its texts, or with
an empty one, cannot be predicted, and the step fails before the worker is asked, as a case
without one of its numbers does (ADR-0114 §3).

## Alternatives

- **A pretrained sentence encoder.** It would tell texts apart by meaning, which the n-gram
  encoder cannot. It needs a library outside DEC-0161, weights from a third party that the
  bench would have to pin and redistribute, and it is a foundation model by any reading of the
  non-goals. Rejected.
- **The hashed n-grams alone, without the encoder.** Deterministic and cheap, but the result is
  not an embedding, and 512 sparse columns per text make a model file of the classifier's weights
  sixteen times larger. Rejected.
- **scikit-learn's multilayer perceptron as the encoder.** It trains with a shuffled stochastic
  order whose bytes depend on the library's internals; full-batch descent in NumPy gives the
  same weights from the same inputs by construction. Rejected.
- **The encoder trained on all rows.** It would have seen the held-out rows' text, so the
  agreement measured on them would overstate. Rejected.

## Consequences

- A step of a process Taktus runs for itself can become a candidate for a move, which the
  `0.4.0` criterion needs.
- A model file of a classifier on text carries a 512 by 32 encoder per text column: about
  200 KB of JSON each.
- Embedding 500 rows takes about two seconds on one processor core.
- The tests that held "a text is left out" now hold "a text is read".

## Where this promise ends

The encoder learns spelling, not meaning. Two texts that share no n-grams are far apart however
alike they mean, and a text with words the training never saw is embedded by the n-grams it
shares with what it did see. A step whose classes depend on meaning more than on wording will not
reach the floor of 95 % agreement, and is proposed nothing; that is the floor working, not a
failure of the move.

The same bytes follow from the same inputs, seed, worker version and library versions on the
same kind of processor. A different BLAS library or processor may round the descent differently
in the last places; the weights are rounded to eight places to absorb that, and that is not
proven across processors here.

The accelerator, and a training that holds one for hours, stopped at an epoch and resumed, are a
tenant's that has an accelerator (DEC-0226). The encoder trains in one step and is not resumable
within it; a stop lands at the step's boundary, before or after it.

The roadmap's criterion still needs a step on Taktus's own instance whose cases reach the floor:
500 labelled cases, 20 in every class, read as numbers or texts. This decision makes such a step
possible; whether one reaches the floor is a fact of the instance's history, stated in
`docs/status/0.4.0.md` once it does.
