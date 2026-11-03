"""The ML bench embeds text with a neural encoder at a pinned version and seed, on an ordinary
processor (#210, ADR-0183, `docs/architecture/methods.md` §1, the row `neural`).

- an `embed` assignment over a text dataset returns the vectors as an artifact, and the same
  inputs at the same worker version and seed return artifacts with the same digests;
- a training names a text column under `inputs.text`: the column is embedded before the
  classifier learns, the model file carries the encoder, and a prediction on raw text embeds it
  exactly as the training did, so that what is served is what was evaluated;
- an encoder that does not fit the bench, or a text column the dataset lacks, is refused.

The accelerator and the hours-long training of #210 are a tenant's that has an accelerator
(DEC-0226); the bench is proven here on the processor it runs on.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import random

import pytest

from .test_mlbench import Bench, bench, digest
from .test_mlbench import ml_bench as ml_bench  # the fixture

TOPICS = {
    "billing": ["invoice", "payment", "amount due", "refund", "remittance"],
    "defect": ["error", "crash", "stack trace", "exception", "fails"],
    "request": ["would like", "please add", "feature", "support for", "option to"],
}
FILLER = "the a when this our we it after before with today again system page".split()


def texts(*, rows: int, seed: int = 1, labelled: bool = True) -> bytes:
    """Short titles, each with two phrases of its topic among filler words."""
    rng = random.Random(seed)  # noqa: S311 — test data drawn from a seed, not a secret
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["title", "length", *(["topic"] if labelled else [])])
    names = sorted(TOPICS)
    for row in range(rows):
        topic = names[row % len(names)]
        words = [rng.choice(FILLER) for _ in range(5)]
        words += [rng.choice(TOPICS[topic]), rng.choice(TOPICS[topic])]
        rng.shuffle(words)
        title = " ".join(words)
        writer.writerow([title, len(title), *([topic] if labelled else [])])
    return out.getvalue().encode()


def test_an_embedding_is_an_artifact_and_the_same_inputs_give_the_same_digest(
    ml_bench: Bench,
) -> None:
    data = texts(rows=120, labelled=False)
    inputs = {"operation": "embed", "dataset": ml_bench.serve("t.csv", data), "text": ["title"]}
    finished, events, first = ml_bench.run(inputs | {"seed": 7})
    assert finished["outcome"] == "succeeded", finished
    kinds = {e["artifact_id"]: e["kind"] for e in events if e["type"] == "artifact.produced"}
    assert kinds == {"embeddings": "dataset", "embedder": "model"}
    vectors = list(csv.reader(io.StringIO(first["embeddings"].decode())))
    assert len(vectors) == 121 and vectors[0][:2] == ["row", "e1"]
    assert len(vectors[0]) == 1 + bench().WIDTH
    encoder = json.loads(first["embedder"])
    assert encoder["seed"] == 7 and encoder["dataset"]["digest"] == digest(data)
    assert encoder["produced_by"]["worker"] == "mlbench"
    assert encoder["text"]["title"]["family"] == "char-ngram-autoencoder"
    _, _, second = ml_bench.run(inputs | {"seed": 7})
    _, _, other = ml_bench.run(inputs | {"seed": 8})
    assert digest(first["embeddings"]) == digest(second["embeddings"])
    assert digest(first["embedder"]) == digest(second["embedder"])
    assert digest(other["embeddings"]) != digest(first["embeddings"]), "the seed is what varies"
    consumed = [e for e in events if e["type"] == "consumption.reported"]
    assert consumed and all(e["resource_class"] == "cpu.small" for e in consumed)


def test_a_training_on_text_learns_from_its_embedding_and_predicts_raw_text(
    ml_bench: Bench,
) -> None:
    data = texts(rows=450)
    inputs = {
        "operation": "train",
        "dataset": ml_bench.serve("train.csv", data),
        "label": "topic",
        "text": ["title"],
        "epochs": 8,
        "seed": 3,
    }
    finished, _, trained = ml_bench.run(inputs)
    assert finished["outcome"] == "succeeded", finished
    model = json.loads(trained["model"])
    assert set(model["text"]) == {"title"}, "the model file carries the encoder"
    assert model["features"][:2] == ["length", "title#1"]
    metrics = json.loads(trained["metrics"])
    assert metrics["accuracy"] >= 0.95, metrics
    _, _, again = ml_bench.run(inputs)
    assert digest(again["model"]) == digest(trained["model"]), "reproducible at the seed"
    unseen = texts(rows=60, seed=9, labelled=False)
    pinned = {"base64": base64.b64encode(trained["model"]).decode()}
    pinned["digest"] = digest(trained["model"])
    finished, _, predicted = ml_bench.run(
        {"operation": "predict", "model": pinned, "dataset": ml_bench.serve("new.csv", unseen)}
    )
    assert finished["outcome"] == "succeeded", finished
    rows = list(csv.DictReader(io.StringIO(predicted["predictions"].decode())))
    expected = [sorted(TOPICS)[k % 3] for k in range(60)]
    right = sum(1 for row, want in zip(rows, expected, strict=True) if row["class"] == want)
    assert right / 60 >= 0.9


def test_what_is_served_is_what_was_evaluated_for_text_too() -> None:
    b = bench()
    table = b.parse_csv(texts(rows=300), "topic", require_label=True, text=("title",))
    prepared = b.prepare(table, 0, 0.2)
    state = None
    for _ in range(6):
        state, _ = b.epoch(prepared, 0, state)
    model = b.load_model(
        b.model_file(prepared, state, seed=0, epochs=6, worker={"worker": "t"}, metrics=None)
    )
    raw = b.parse_csv(texts(rows=300), "topic", require_label=False, text=("title",))
    served, _ = b.predict(model, b.columns(model, raw))
    measured, _ = b.predict(model, prepared.x_holdout)
    assert len(served) == 300 and len(measured) == 60
    # A held-out row is served as it was measured: embedded by the encoder in the file.
    embedded = b.with_text(raw.x, raw.texts, model.text)
    assert embedded.shape == (300, 1 + b.WIDTH)


def test_an_encoder_or_a_text_column_that_does_not_fit_is_refused() -> None:
    b = bench()
    with pytest.raises(b.BenchError, match="no text column 'subject'"):
        b.parse_csv(texts(rows=10), "topic", require_label=True, text=("subject",))
    with pytest.raises(b.BenchError, match="label and a text"):
        b.parse_csv(texts(rows=10), "topic", require_label=True, text=("topic",))
    encoder = b.fit_embedder(["one text", "another"], 0)
    with pytest.raises(b.BenchError, match="counts its n-grams otherwise"):
        b.check_embedder(encoder | {"buckets": 7})
    with pytest.raises(b.BenchError, match="do not fit its width"):
        b.check_embedder(encoder | {"width": 3})
    with pytest.raises(b.BenchError, match="at least one row"):
        b.fit_embedder([], 0)
