"""What a prediction returned, read, and the step's confidence in it (ADR-0076).

A worker that offers `ml.predict` returns its predictions as a CSV with a header row and the
columns `row`, `class` and `confidence`: one line per row of the step's dataset, its class, and
the probability the model gives that class (NTC-0156). The step's confidence is the lowest of
its rows: a step hands its result on as one, so one unsure row makes the step unsure.

Pure: bytes in, rows and a number out.
"""

from __future__ import annotations

import csv
import io
import math

from taktus.shared.v1 import Value

ARTIFACT = "predictions"
"""The artifact a prediction produces (`workers/mlbench/README.md`, the operation `predict`)."""
COLUMNS = ("row", "class", "confidence")


class Unreadable(Exception):
    """The predictions are not what a prediction returns; the step fails with this reason."""


class Row(Value):
    row: int
    label: str
    confidence: float

    def document(self) -> dict[str, object]:
        return {"row": self.row, "class": self.label, "confidence": self.confidence}


def rows(content: bytes | None) -> tuple[Row, ...]:
    """Every row of the predictions, in order, or Unreadable naming what is wrong. A prediction
    of no row is unreadable: a step without a row has no confidence."""
    if content is None:
        raise Unreadable(f"the worker produced no artifact {ARTIFACT!r}")
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8")))
        header = next(reader, None)
        if header is None or tuple(header) != COLUMNS:
            raise Unreadable(f"the predictions do not start with the header {','.join(COLUMNS)}")
        read: list[Row] = []
        for line in reader:
            if not line:
                continue
            number, label, confidence = line
            value = float(confidence)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise Unreadable(f"row {number}: confidence {confidence} is not from 0 to 1")
            read.append(Row(row=int(number), label=label, confidence=value))
    except (UnicodeDecodeError, ValueError) as error:
        raise Unreadable(f"the predictions cannot be read: {error}") from error
    if not read:
        raise Unreadable("the prediction holds no row, so the step has no confidence")
    return tuple(read)


def lowest(read: tuple[Row, ...]) -> float:
    """The step's confidence: the lowest of its rows (ADR-0076 §2)."""
    return min(row.confidence for row in read)
