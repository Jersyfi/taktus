"""The ML bench's own work: datasets, one epoch of training, the model file, evaluation, prediction.

Nothing here knows the worker contract; `worker.py` calls these functions as the steps of an
assignment. The model family is a linear classifier — logistic regression fitted by stochastic
gradient descent, one pass over the training split per epoch — on standardised features.

**Reproducible at a pinned version.** Every random choice takes the task's seed: the synthetic
dataset, the held-out split and the order of each epoch. The model file is JSON whose bytes are
fixed by the training: the same dataset, seed and worker version give the same bytes, and so the
same digest. The state after an epoch is the classifier's weights and its step counter, so that a
resumed training continues exactly where it stopped and ends in the same model as one that ran
straight through (`tests/workers/test_mlbench.py`).

**What is served is what was evaluated.** The metrics of a training are computed by `predict`
over the model file as it was written, the same function a prediction assignment calls — never
by the in-memory classifier. A file that would predict differently than it was measured cannot
leave the bench.

**Text becomes numbers through a neural embedding** (ADR-0183). A column the task names as
text is embedded before the classifier sees it: its character n-grams are hashed into a fixed
number of buckets, and a one-layer neural encoder, trained as an autoencoder on the training
rows' text from the seed, maps them to a short vector. The encoder's weights travel in the model
file, so that a prediction embeds a row exactly as the training did. The `embed` operation
returns the encoder and the vectors on their own. The encoder learns from the dataset alone: it
is no pretrained language model (`docs/vision/non-goals.md`), and it knows no word it has not
seen.

The model file holds numbers only. Loading it runs no code: it is never a pickle.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import sklearn
from sklearn.datasets import make_classification
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
from sklearn.metrics import precision_recall_fscore_support as prfs
from sklearn.model_selection import train_test_split

type Json = dict[str, Any]

MODEL_FORMAT = "taktus.mlbench.linear/1"
EMBEDDER_FORMAT = "taktus.mlbench.embedder/1"
EMBEDDER_FAMILY = "char-ngram-autoencoder"
BUCKETS = 512  # the hashed character n-grams a text is counted in
WIDTH = 32  # the length of an embedding
NGRAMS = (2, 4)  # the shortest and the longest n-gram counted
ITERATIONS = 800  # full passes of gradient descent over the training rows' text
RATE = 0.3  # the step size of each pass
DECIMALS = 8  # the encoder's weights are rounded to this, so that its bytes are its digest
FAMILY = "logistic-regression-sgd"
ALPHA = 1e-4  # the regularisation strength; part of the family, not of the task


class BenchError(Exception):
    """The work cannot go on, and why — in words the assignment's reason carries."""


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def libraries() -> Json:
    """The library versions a model file records: with the worker's version they are the pin."""
    return {"numpy": np.__version__, "scikit-learn": sklearn.__version__}


# --- datasets -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Table:
    """A dataset as read: feature columns by name, and the label column when there is one."""

    features: tuple[str, ...]
    x: np.ndarray
    label: str | None
    y: np.ndarray | None
    digest: str
    texts: dict[str, list[str]] = field(default_factory=dict)
    """The text columns by name, each a list of its rows' text, kept apart from `x`."""


def synthetic(spec: Json, seed: int) -> tuple[bytes, Table]:
    """The built-in dataset: a classification problem drawn from the seed. Its bytes are the CSV
    it would be as a file, so that its digest means the same as a file's."""
    rows = int(spec.get("rows", 2000))
    width = int(spec.get("features", 8))
    classes = int(spec.get("classes", 3))
    if not (10 <= rows <= 5_000_000 and 2 <= width <= 1000 and 2 <= classes <= 50):
        raise BenchError(
            "a synthetic dataset has 10 to 5000000 rows, 2 to 1000 features, 2 to 50 classes"
        )
    x, y = make_classification(
        n_samples=rows,
        n_features=width,
        n_informative=max(2, min(width, (width * 2) // 3)),
        n_redundant=0,
        n_classes=classes,
        n_clusters_per_class=1,
        random_state=seed,
    )
    names = tuple(f"x{k}" for k in range(1, width + 1))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([*names, "label"])
    for features, label in zip(x.tolist(), y.tolist(), strict=True):
        writer.writerow([repr(v) for v in features] + [f"c{label}"])
    data = out.getvalue().encode()
    return data, parse_csv(data, "label", require_label=True)


def parse_csv(
    data: bytes, label: str | None, *, require_label: bool, text: tuple[str, ...] = ()
) -> Table:
    """A CSV with a header row and numbers in every feature column. `label` names the label
    column; None means the last column when a label is required, and no label otherwise. The
    columns `text` names hold text, kept as read for the embedding."""
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BenchError("the dataset is not UTF-8 text") from error
    rows = list(csv.reader(io.StringIO(decoded)))
    if len(rows) < 2:
        raise BenchError("the dataset has no rows under its header")
    header = [h.strip() for h in rows[0]]
    if len(set(header)) != len(header):
        raise BenchError("the dataset's header names a column twice")
    if label is None and require_label:
        label = header[-1]
    if label is not None and label not in header:
        if require_label:
            raise BenchError(f"the dataset has no label column {label!r}")
        label = None
    where = header.index(label) if label is not None else -1
    missing = [name for name in text if name not in header]
    if missing:
        raise BenchError(f"the dataset has no text column {missing[0]!r}")
    if label is not None and label in text:
        raise BenchError(f"the column {label!r} cannot be the label and a text at once")
    texts_at = [header.index(name) for name in text]
    numeric_at = [k for k in range(len(header)) if k != where and k not in texts_at]
    names = tuple(header[k] for k in numeric_at)
    if not names and not text:
        raise BenchError("the dataset has no feature column")
    values: list[list[float]] = []
    labels: list[str] = []
    texts: dict[str, list[str]] = {name: [] for name in text}
    for number, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        if len(row) != len(header):
            raise BenchError(f"line {number} has {len(row)} fields, the header {len(header)}")
        try:
            values.append([float(row[k]) for k in numeric_at])
        except ValueError as error:
            raise BenchError(f"line {number} holds a feature that is not a number") from error
        for name, k in zip(text, texts_at, strict=True):
            texts[name].append(row[k])
        if where >= 0:
            labels.append(row[where].strip())
    x = np.asarray(values, dtype=np.float64).reshape(len(values), len(numeric_at))
    if not np.isfinite(x).all():
        raise BenchError("the dataset holds a feature that is not finite")
    y = np.asarray(labels) if where >= 0 else None
    return Table(names, x, label, y, sha256(data), texts)


# --- text, embedded ----------------------------------------------------------------------------


def grams(text: str) -> list[str]:
    """The character n-grams of a text, lower-cased, its white space folded to one blank and a
    blank at either end, so that a word's start and end are n-grams of their own."""
    folded = " " + " ".join(text.lower().split()) + " "
    low, high = NGRAMS
    return [folded[k : k + n] for n in range(low, high + 1) for k in range(len(folded) - n + 1)]


def _bucket(gram: str) -> int:
    """A stable hash, the same on every machine and in every process: never Python's `hash`."""
    return int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big") % BUCKETS


def hashed(texts: list[str]) -> np.ndarray:
    """Every text as the counts of its n-grams per bucket, scaled to length one."""
    counts = np.zeros((len(texts), BUCKETS), dtype=np.float64)
    for row, text in enumerate(texts):
        for gram in grams(text):
            counts[row, _bucket(gram)] += 1.0
    norms = np.linalg.norm(counts, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return counts / norms


def fit_embedder(texts: list[str], seed: int) -> Json:
    """A one-layer neural encoder, trained as an autoencoder on these texts from the seed: the
    hashed n-grams in, a `WIDTH`-long tanh layer, the n-grams again out, the squared error
    reduced by full-batch gradient descent for `ITERATIONS` passes. Its weights are rounded,
    so that the same texts and seed give the same bytes."""
    if not texts:
        raise BenchError("an embedding needs at least one row of text")
    x = hashed(texts)
    rows = x.shape[0]
    rng = np.random.default_rng(seed)
    w = rng.normal(0.0, 1.0 / np.sqrt(BUCKETS), (BUCKETS, WIDTH))
    b = np.zeros(WIDTH)
    v = rng.normal(0.0, 1.0 / np.sqrt(BUCKETS), (WIDTH, BUCKETS))
    c = np.zeros(BUCKETS)
    loss = 0.0
    for _ in range(ITERATIONS):
        h = np.tanh(x @ w + b)
        error = h @ v + c - x
        loss = float((error**2).sum() / rows)
        grad_out = 2.0 * error / rows
        grad_hidden = (grad_out @ v.T) * (1.0 - h * h)
        v -= RATE * (h.T @ grad_out)
        c -= RATE * grad_out.sum(axis=0)
        w -= RATE * (x.T @ grad_hidden)
        b -= RATE * grad_hidden.sum(axis=0)
    if not np.isfinite(loss) or not np.isfinite(w).all():
        raise BenchError("the embedding did not converge on this text: its error is not finite")
    return {
        "format": EMBEDDER_FORMAT,
        "family": EMBEDDER_FAMILY,
        "buckets": BUCKETS,
        "ngrams": list(NGRAMS),
        "width": WIDTH,
        "seed": seed,
        "iterations": ITERATIONS,
        "rows": rows,
        "loss": round(loss, 9),
        "w": np.round(w, DECIMALS).tolist(),
        "b": np.round(b, DECIMALS).tolist(),
    }


def check_embedder(document: Any) -> Json:
    """An encoder document as read, or a BenchError naming what is wrong with it."""
    if not isinstance(document, dict) or document.get("format") != EMBEDDER_FORMAT:
        raise BenchError(f"the embedder is not of the format {EMBEDDER_FORMAT}")
    if document.get("buckets") != BUCKETS or document.get("ngrams") != list(NGRAMS):
        raise BenchError("the embedder counts its n-grams otherwise than this bench does")
    try:
        w = np.asarray(document["w"], dtype=np.float64)
        b = np.asarray(document["b"], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as error:
        raise BenchError("the embedder is incomplete") from error
    width = int(document.get("width", 0))
    if w.shape != (BUCKETS, width) or b.shape != (width,):
        raise BenchError("the embedder's weights do not fit its width")
    return document


def embed(document: Json, texts: list[str]) -> np.ndarray:
    """The texts as vectors, through the encoder's rounded weights alone."""
    w = np.asarray(document["w"], dtype=np.float64)
    b = np.asarray(document["b"], dtype=np.float64)
    return np.tanh(hashed(texts) @ w + b)


def embedded_names(column: str, width: int) -> list[str]:
    return [f"{column}#{k}" for k in range(1, width + 1)]


def embeddings_csv(vectors: np.ndarray) -> bytes:
    """The vectors as a dataset: one row per text, in the order read, each value to 9 places."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["row", *(f"e{k}" for k in range(1, vectors.shape[1] + 1))])
    for row, vector in enumerate(vectors.tolist(), 1):
        writer.writerow([row, *(f"{value:.9f}" for value in vector)])
    return out.getvalue().encode()


def with_text(x: np.ndarray, texts: dict[str, list[str]], embedders: dict[str, Json]) -> np.ndarray:
    """The numeric columns, then each text column's embedding in the order of its name."""
    parts = [x] + [embed(embedders[name], texts[name]) for name in sorted(embedders)]
    return np.hstack(parts) if len(parts) > 1 else x


# --- training -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Prepared:
    """A training's data after the split: the training rows standardised, the held-out rows as
    read, and what the model file records about them."""

    features: tuple[str, ...]
    label: str
    classes: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    x_train: np.ndarray
    y_train: np.ndarray
    x_holdout: np.ndarray
    y_holdout: np.ndarray
    digest: str
    rows: int
    embedders: dict[str, Json] = field(default_factory=dict)
    """The encoder of every text column, trained on the training rows' text alone."""


def prepare(table: Table, seed: int, holdout: float) -> Prepared:
    if table.y is None or table.label is None:
        raise BenchError("a training needs a label column")
    if not 0.05 <= holdout <= 0.5:
        raise BenchError("the held-out share is between 0.05 and 0.5")
    classes = tuple(sorted(set(table.y.tolist())))
    if len(classes) < 2:
        raise BenchError("a training needs at least two classes")
    counts = [int((table.y == c).sum()) for c in classes]
    stratify = table.y if min(counts) >= 2 else None
    index = np.arange(table.y.shape[0])
    train_at, holdout_at = train_test_split(
        index, test_size=holdout, random_state=seed, stratify=stratify
    )
    embedders = {
        name: fit_embedder([rows[k] for k in train_at.tolist()], seed)
        for name, rows in sorted(table.texts.items())
    }
    x = with_text(table.x, table.texts, embedders)
    features = table.features + tuple(
        n for name in sorted(embedders) for n in embedded_names(name, WIDTH)
    )
    x_train, x_holdout = x[train_at], x[holdout_at]
    y_train, y_holdout = table.y[train_at], table.y[holdout_at]
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale == 0.0] = 1.0
    return Prepared(
        features,
        table.label,
        classes,
        mean,
        scale,
        (x_train - mean) / scale,
        y_train,
        x_holdout,
        y_holdout,
        table.digest,
        int(table.x.shape[0]),
        embedders,
    )


def classifier(seed: int, classes: tuple[str, ...], state: Json | None) -> SGDClassifier:
    """The classifier at the start of a training, or as an epoch's state left it."""
    model = SGDClassifier(loss="log_loss", alpha=ALPHA, random_state=seed)
    if state is not None:
        model.coef_ = np.asarray(state["coef"], dtype=np.float64)
        model.intercept_ = np.asarray(state["intercept"], dtype=np.float64)
        model.t_ = float(state["t"])
        model.classes_ = np.asarray(classes)
        model.n_features_in_ = model.coef_.shape[1]
    return model


def epoch(data: Prepared, seed: int, state: Json | None) -> tuple[Json, float]:
    """One pass over the training rows, from the state the last epoch left: the new state and
    the training loss after it."""
    model = classifier(seed, data.classes, state)
    model.partial_fit(data.x_train, data.y_train, classes=np.asarray(data.classes))
    loss = float(log_loss(data.y_train, model.predict_proba(data.x_train), labels=data.classes))
    after: Json = {
        "coef": model.coef_.tolist(),
        "intercept": model.intercept_.tolist(),
        "t": float(model.t_),
    }
    return after, loss


def model_file(
    data: Prepared, state: Json, *, seed: int, epochs: int, worker: Json, metrics: Json | None
) -> bytes:
    """The model as a file: everything prediction needs, and what produced it."""
    document: Json = {
        "format": MODEL_FORMAT,
        "family": FAMILY,
        "produced_by": {**worker, "libraries": libraries()},
        "seed": seed,
        "epochs": epochs,
        "dataset": {"digest": data.digest, "rows": data.rows, "label": data.label},
        "features": list(data.features),
        "classes": list(data.classes),
        "scaler": {"mean": data.mean.tolist(), "scale": data.scale.tolist()},
        "coef": state["coef"],
        "intercept": state["intercept"],
    }
    if data.embedders:
        document["text"] = data.embedders
    if metrics is not None:
        document["evaluation"] = metrics
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


# --- the model file served ------------------------------------------------------------------------


@dataclass(frozen=True)
class Model:
    features: tuple[str, ...]
    classes: tuple[str, ...]
    label: str
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray
    intercept: np.ndarray
    text: dict[str, Json] = field(default_factory=dict)
    """The encoder of every text column the model reads, by the column's name."""

    @property
    def numeric(self) -> tuple[str, ...]:
        """The features read as numbers: every feature no text column's embedding gives."""
        embedded = {n for name, e in self.text.items() for n in embedded_names(name, e["width"])}
        return tuple(name for name in self.features if name not in embedded)


def load_model(data: bytes) -> Model:
    try:
        document = json.loads(data)
    except ValueError as error:
        raise BenchError("the model is not JSON") from error
    if not isinstance(document, dict) or document.get("format") != MODEL_FORMAT:
        raise BenchError(f"the model is not of the format {MODEL_FORMAT}")
    try:
        model = Model(
            tuple(document["features"]),
            tuple(document["classes"]),
            str(document["dataset"]["label"]),
            np.asarray(document["scaler"]["mean"], dtype=np.float64),
            np.asarray(document["scaler"]["scale"], dtype=np.float64),
            np.asarray(document["coef"], dtype=np.float64),
            np.asarray(document["intercept"], dtype=np.float64),
            {
                str(name): check_embedder(embedder)
                for name, embedder in (document.get("text") or {}).items()
            },
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise BenchError("the model file is incomplete") from error
    width = len(model.features)
    rows = 1 if len(model.classes) == 2 else len(model.classes)
    if model.coef.shape != (rows, width) or model.intercept.shape != (rows,):
        raise BenchError("the model's weights do not fit its features and classes")
    return model


def columns(model: Model, table: Table) -> np.ndarray:
    """The table's feature columns in the order the model was trained on, each text column
    embedded by the model's own encoder."""
    missing = [name for name in model.numeric if name not in table.features]
    missing += [name for name in sorted(model.text) if name not in table.texts]
    if missing:
        raise BenchError(f"the dataset lacks the model's feature {missing[0]!r}")
    order = [table.features.index(name) for name in model.numeric]
    return with_text(table.x[:, order], table.texts, model.text)


def predict(model: Model, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each row's class and its probability, from the model file's numbers alone: the scores
    of the linear model, the logistic of each, normalised across the classes one against the
    rest — as the classifier computes them."""
    scores = ((x - model.mean) / model.scale) @ model.coef.T + model.intercept
    classes = np.asarray(model.classes)
    if len(model.classes) == 2:
        p1 = 1.0 / (1.0 + np.exp(-scores[:, 0]))
        probability = np.column_stack([1.0 - p1, p1])
        chosen = (scores[:, 0] > 0).astype(int)
    else:
        probability = 1.0 / (1.0 + np.exp(-scores))
        total = probability.sum(axis=1, keepdims=True)
        uniform = total[:, 0] == 0.0
        total[uniform] = 1.0
        probability = probability / total
        probability[uniform] = 1.0 / len(model.classes)
        chosen = scores.argmax(axis=1)
    return classes[chosen], probability[np.arange(len(chosen)), chosen]


def evaluate(model: Model, x: np.ndarray, y: np.ndarray) -> Json:
    """The metrics of a model on labelled rows, through `predict`."""
    predicted, _ = predict(model, x)
    labels = list(model.classes)
    precision, recall, f1, support = prfs(y, predicted, labels=labels, zero_division=0)
    return {
        "rows": len(y),
        "accuracy": round(float(accuracy_score(y, predicted)), 6),
        "macro_f1": round(
            float(f1_score(y, predicted, labels=labels, average="macro", zero_division=0)), 6
        ),
        "per_class": {
            label: {
                "precision": round(float(precision[k]), 6),
                "recall": round(float(recall[k]), 6),
                "f1": round(float(f1[k]), 6),
                "support": int(support[k]),
            }
            for k, label in enumerate(labels)
        },
        "confusion": {
            "labels": labels,
            "matrix": confusion_matrix(y, predicted, labels=labels).tolist(),
        },
    }


def predictions_csv(classes: np.ndarray, confidence: np.ndarray) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["row", "class", "confidence"])
    for row, (label, p) in enumerate(zip(classes.tolist(), confidence.tolist(), strict=True), 1):
        writer.writerow([row, label, f"{p:.6f}"])
    return out.getvalue().encode()
