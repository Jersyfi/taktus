"""Weighing: the Takt of a breakdown at a weighting table (ADR-0010).

The Takt is the same breakdown money is computed from, taken at a weighting table instead of a
price table: tokens per model and price kind times the model's class factor, compute minutes
per resource class, finished steps of the methods the table weighs per step, and MiB of state
written. Which class a model is in is the operator's, recorded with the run; the table gives the
factor of each class. A quantity the table does not weigh is named, never counted as zero
(UC-8.5). Pure: a meter and a table in, a Takt out.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from taktus.components.accounting.domain.service.metering import Meter
from taktus.ports.model import WeightingTable, entry_for
from taktus.shared.v1 import Method, Value

WEIGHED_ELSEWHERE = frozenset({"llm", "ml", "neural", "worker"})
"""Methods whose work the table weighs by what they used — an `llm` step by its tokens, an
`ml`, `neural` or `worker` step by its compute — not by their number."""

MIB = 1024 * 1024


class Takt(Value):
    """A breakdown at one weighting table: the Takte, their parts, and what was not weighed."""

    takte: float
    table: str
    """The version of the table the Takte were computed at."""
    calibrated: bool
    calibration: Literal["calibrated", "uncalibrated"]
    """The word every figure carries: `uncalibrated` until the weights are fixed."""
    tokens: float = 0.0
    compute: float = 0.0
    steps: float = 0.0
    storage: float = 0.0
    unweighed: tuple[str, ...] = ()
    """What the Takte leave out, and why: never counted as zero."""


def calibration(calibrated: bool) -> Literal["calibrated", "uncalibrated"]:
    """The word beside a figure of a table: `uncalibrated` until its weights are fixed."""
    return "calibrated" if calibrated else "uncalibrated"


def weigh(used: Meter, table: WeightingTable, model_classes: Mapping[str, str]) -> Takt:
    """The Takte of the breakdown at the table, with every model weighed at the factor of the
    class `model_classes` puts it in — a dated model in the class of its undated name where
    no class names the dated one (`entry_for`)."""
    unweighed: list[str] = []
    tokens = 0.0
    for model, kinds in sorted(used.tokens.items()):
        model_class = entry_for(model, model_classes)
        factor = None if model_class is None else table.model_classes.get(model_class)
        counted = sum(
            getattr(kinds, kind) or 0 for kind in ("input", "output", "cache_read", "cache_write")
        )
        if model_class is None:
            unweighed.append(f"{counted} token(s) of {model}: the model is in no class")
            continue
        if factor is None:
            unweighed.append(
                f"{counted} token(s) of {model}: table {table.version} gives the class "
                f"{model_class} no factor"
            )
            continue
        for kind in ("input", "output", "cache_read", "cache_write"):
            count = getattr(kinds, kind)
            if not count:
                continue
            weight = table.tokens.get(kind)
            if weight is None:
                unweighed.append(f"{model} {kind}: table {table.version} gives the kind no weight")
                continue
            tokens += count / table.unit_tokens * weight * factor
    if used.tokens_unattributed:
        unweighed.append(
            f"{used.tokens_unattributed} token(s) recorded without the model that used them"
        )
    compute = 0.0
    for resource_class, seconds in sorted(used.compute_seconds.items()):
        if not seconds:
            continue
        per_minute = table.compute_per_minute.get(resource_class)
        if per_minute is None:
            unweighed.append(
                f"{seconds:.3f}s of compute {resource_class}: table {table.version} gives the "
                "class no weight"
            )
            continue
        compute += seconds / 60 * per_minute
    steps = 0.0
    for method, count in sorted(used.steps.items()):
        per_step = table.steps.get(Method(method))
        if per_step is not None:
            steps += count * per_step
        elif method not in WEIGHED_ELSEWHERE:
            unweighed.append(
                f"{count} {method} step(s): table {table.version} gives the method no weight"
            )
    storage = used.storage_bytes / MIB * table.storage_per_mib
    return Takt(
        takte=round(tokens + compute + steps + storage, 9),
        table=table.version,
        calibrated=table.calibrated,
        calibration=calibration(table.calibrated),
        tokens=round(tokens, 9),
        compute=round(compute, 9),
        steps=round(steps, 9),
        storage=round(storage, 9),
        unweighed=tuple(unweighed),
    )
