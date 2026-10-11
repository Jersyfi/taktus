"""A step on a trained model registers only with the model's evaluation (UC-8.4 §2, ADR-0092).

UC-8.4 says that a change of the model a step uses registers only with an evaluation, and that a
change that fails it stays out of production. A process version pins the model of every step of
method `ml` by the digest of its file. This module holds each such step to carrying, in its
work, how that very file did on cases held out from its training:

- `model_digest`: the digest of the file evaluated, the one the step pins;
- `held_out`: how many cases it was evaluated on, at least one;
- `agreement`: the share of them on which it gave the label, from 0 to 1;
- `below_threshold`: the share of them below the step's confidence threshold, from 0 to 1;
- `trial_run`: the run that predicted them, where the evaluation can be read back.

A model named by a reference — `{ $input: ... }` — is known only when a run resolves it; its
digest cannot be held against the evaluation's here, and the version is refused: an evaluation
must say which file it is about.

Pure: the version's steps and work in, findings out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from taktus.shared.v1 import Method, Step

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def findings(steps: Sequence[Step], work: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Why the version's steps on a trained model may not register; empty when they may."""
    found: list[str] = []
    for step in steps:
        if step.method is not Method.ML:
            continue
        found.extend(f"step {step.id!r}: {f}" for f in _of(work.get(step.id) or {}))
    return found


def _of(work: Mapping[str, Any]) -> list[str]:
    evaluation = work.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return [
            "a step on a trained model registers only with the model's evaluation on cases held "
            "out from its training, under `work.evaluation` (UC-8.4 §2): model_digest, held_out, "
            "agreement, below_threshold, trial_run"
        ]
    found: list[str] = []
    model = work.get("model")
    pinned = model.get("digest") if isinstance(model, Mapping) else None
    evaluated = evaluation.get("model_digest")
    if not isinstance(evaluated, str) or DIGEST.match(evaluated) is None:
        found.append("the evaluation names no model by its digest under `model_digest`")
    elif not isinstance(pinned, str):
        found.append(
            "the step's model is not pinned by a digest in the version, so the evaluation "
            "cannot be held against it"
        )
    elif evaluated != pinned:
        found.append(
            f"the evaluation is of the model {evaluated}, and the step pins {pinned}: a model "
            "registers only with its own evaluation"
        )
    held = evaluation.get("held_out")
    if isinstance(held, bool) or not isinstance(held, int) or held < 1:
        found.append("the evaluation names how many held-out cases it was made on, at least one")
    for share in ("agreement", "below_threshold"):
        value = evaluation.get(share)
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
            found.append(f"the evaluation's `{share}` is a share from 0 to 1")
    trial = evaluation.get("trial_run")
    if not isinstance(trial, str) or not trial:
        found.append("the evaluation names the run that made it under `trial_run`")
    return found
