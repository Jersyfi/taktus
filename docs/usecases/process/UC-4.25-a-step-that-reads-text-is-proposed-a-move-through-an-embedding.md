---
id: UC-4.25
title: A step that reads text is proposed a move through an embedding
component: process
epic: E4
serves: [P2, P8]
state: building
version: 0.4.0
tests: [tests/workers/test_mlbench_embeddings.py::test_an_embedding_is_an_artifact_and_the_same_inputs_give_the_same_digest, tests/workers/test_mlbench_embeddings.py::test_a_training_on_text_learns_from_its_embedding_and_predicts_raw_text, tests/workers/test_mlbench_embeddings.py::test_what_is_served_is_what_was_evaluated_for_text_too, tests/workers/test_mlbench_embeddings.py::test_an_encoder_or_a_text_column_that_does_not_fit_is_refused, tests/workers/test_maturation_on_text.py::test_a_step_that_reads_text_is_proposed_a_model_the_bench_trained_on_its_embedding, tests/workers/test_maturation_on_text.py::test_the_moved_step_predicts_its_text_case_and_falls_back_on_an_empty_text]
adrs: {ADR-0007: 26804369941b, ADR-0084: b792ae358b77, ADR-0114: 75a031083f19, ADR-0183: db4da8845438}
supersedes: null
---

# UC-4.25 — A step that reads text is proposed a move through an embedding

## 1. What must be achieved

Most steps that run on a language model read text, not numbers: a title, a message, a
description. UC-4.24 proposes a cheaper method only for a step whose inputs are numbers. A step
that reads text must be able to reach the same proposal, by way of an embedding: a neural model
that turns each text into numbers, at a pinned version and seed, so that a trained classifier can
learn from them.

1. **Text is embedded reproducibly.** The ML bench turns the texts of a dataset into vectors with
   a neural model it trains on the dataset itself, on an ordinary processor. The same texts, seed
   and worker version give vectors and a model with the same digests.
2. **What a step read as text is learned from.** A step's case gives its texts beside its numbers.
   A step whose cases all give the same numbers and texts, and at least one of either, is held to
   every other floor of UC-4.24, unchanged.
3. **What is served is what was evaluated.** The model a proposal names carries its embedding. A
   moved step embeds its case's text with the very model its version pins, never another.

## 2. How it is verified

- **Requirement 1.** An embedding assignment over a text dataset returns the vectors as an
  artifact; the same inputs at the same seed return artifacts with the same digests, and another
  seed returns other vectors. Its consumption is reported in the bench's resource class.
- **Requirement 2.** A step on a language model whose prompt reads only text is proposed a model
  the bench trained on the texts' embedding, when its cases reach UC-4.24's floor; the proposal
  names the texts it reads.
- **Requirement 3.** A training on text writes the embedding into the model file, and a prediction
  on unseen raw text through that file gives the classes; a moved step predicts its one case with
  its text through the pinned file, and a case whose text is missing or empty is not predicted.

## 3. Where the boundary lies

**Not a pretrained or foundation model** (`docs/vision/non-goals.md`): the embedding learns from
the dataset alone, and tells texts apart by their wording, not by their meaning. **Not an
accelerator**: a training that holds one for hours is a tenant's that has one (DEC-0226). **Not
images, speech or time series.** Every floor and every person's act of UC-4.24 stays as it is.

## 4. What it rests on

Method maturation (UC-4.24, ADR-0084, ADR-0114); the ML bench (ADR-0007, ADR-0076); the method
kind `neural` (`docs/architecture/methods.md` §1). ADR-0183 builds all three requirements
(issues #210 and #218). The roadmap's `0.4.0` criterion needs a step of a process Taktus runs
moved on its own proposal; every such step reads text, so it rests on this use case.

## 5. What is proven so far

By the named tests: the bench's embedding is reproducible at its seed and an artifact; a training
on text reaches the agreement on held-out rows and predicts unseen raw text through its file; an
encoder or a text column that does not fit is refused. Against the bench itself, a step on a
language model that reads only text is proposed a model trained on its embedding, and the moved
step predicts its text case through the pinned file.

Not yet: a step of a process Taktus runs on its own instance with 500 labelled cases. That is a
fact of the instance's history, not of the code.
