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

The model file holds numbers only. Loading it runs no code: it is never a pickle.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
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


def parse_csv(data: bytes, label: str | None, *, require_label: bool) -> Table:
    """A CSV with a header row and numbers in every feature column. `label` names the label
    column; None means the last column when a label is required, and no label otherwise."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BenchError("the dataset is not UTF-8 text") from error
    rows = list(csv.reader(io.StringIO(text)))
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
    names = tuple(h for k, h in enumerate(header) if k != where)
    if not names:
        raise BenchError("the dataset has no feature column")
    values: list[list[float]] = []
    labels: list[str] = []
    for number, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        if len(row) != len(header):
            raise BenchError(f"line {number} has {len(row)} fields, the header {len(header)}")
        try:
            values.append([float(v) for k, v in enumerate(row) if k != where])
        except ValueError as error:
            raise BenchError(f"line {number} holds a feature that is not a number") from error
        if where >= 0:
            labels.append(row[where].strip())
    x = np.asarray(values, dtype=np.float64)
    if not np.isfinite(x).all():
        raise BenchError("the dataset holds a feature that is not finite")
    y = np.asarray(labels) if where >= 0 else None
    return Table(names, x, label, y, sha256(data))


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
    x_train, x_holdout, y_train, y_holdout = train_test_split(
        table.x, table.y, test_size=holdout, random_state=seed, stratify=stratify
    )
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale == 0.0] = 1.0
    return Prepared(
        table.features,
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
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BenchError("the model file is incomplete") from error
    width = len(model.features)
    rows = 1 if len(model.classes) == 2 else len(model.classes)
    if model.coef.shape != (rows, width) or model.intercept.shape != (rows,):
        raise BenchError("the model's weights do not fit its features and classes")
    return model


def columns(model: Model, table: Table) -> np.ndarray:
    """The table's feature columns in the order the model was trained on."""
    missing = [name for name in model.features if name not in table.features]
    if missing:
        raise BenchError(f"the dataset lacks the model's feature {missing[0]!r}")
    order = [table.features.index(name) for name in model.features]
    return table.x[:, order]


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
