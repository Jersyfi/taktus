"""The rules of an evaluation (UC-4.18, ADR-0134 §2, §4, §7). Pure.

- **A score.** A rule scorer holds a result's text to its target: `equals`, `contains`,
  `pattern` or `overlap`. Text is compared after case folding, with every run of white space
  taken as one space.
- **A judge's answer.** A judge's model answers one number from 0 to 1; anything else is no
  score, and the judge falls back.
- **The verdict.** A change is `incomplete`, `regressed` or `passed`; a drift evaluation is
  `incomplete`, `first`, `drift` or `steady`. The tenant's tolerance is the only threshold.
- **Which proposals are evaluated.** One whose difference touches a step.
- **A case from a correction.** The run's inputs, reduced to those the version's steps read;
  and the inputs a step's scope names as its subject, which are personal by declaration
  (ADR-0130 §2).

Each is a rule: the same facts give the same answer every time, and a person can recompute it
from what the evaluation records (ADR-0023).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from taktus.components.process.domain.model.evaluation import (
    CaseResult,
    ScoringRule,
    Side,
    SideResult,
    Verdict,
)
from taktus.components.process.domain.model.process import ProcessVersion
from taktus.components.process.domain.model.proposal import Difference

INPUT = "$input"
WORD = re.compile(r"\w+")
JUDGED = re.compile(r"^\s*(0(?:\.\d+)?|1(?:\.0+)?|\.\d+)\s*$")
"""A judge's answer: one number from 0 to 1, and nothing else."""


def text_of(value: Any) -> str:
    """The text a result or a target is compared as: a string as it is, anything else as its
    canonical JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normal(text: str) -> str:
    return " ".join(text.casefold().split())


def score(rule: ScoringRule, result: str, target: Any) -> float:
    """The score of a result against its target by one rule, from 0 to 1."""
    found = normal(result)
    wanted = normal(text_of(target))
    if rule.kind == "equals":
        return 1.0 if found == wanted else 0.0
    if rule.kind == "contains":
        return 1.0 if wanted in found else 0.0
    if rule.kind == "pattern":
        return 1.0 if re.search(rule.pattern or "", result) is not None else 0.0
    return overlap(found, wanted)


def overlap(result: str, target: str) -> float:
    """The F1 of the two texts' sets of words: 1 when they share every word, 0 when none."""
    have = set(WORD.findall(result))
    want = set(WORD.findall(target))
    if not have and not want:
        return 1.0
    common = len(have & want)
    if common == 0:
        return 0.0
    precision = common / len(have)
    recall = common / len(want)
    return round(2 * precision * recall / (precision + recall), 6)


def judged(answer: str) -> float | None:
    """The score a judge's model answered; None when the answer is not one number from 0 to 1."""
    match = JUDGED.match(answer)
    return None if match is None else float(match.group(1))


def mean(values: Iterable[float | None]) -> float | None:
    """The mean; None when a value is None or there is none."""
    found = list(values)
    if not found or any(value is None for value in found):
        return None
    return round(sum(v for v in found if v is not None) / len(found), 6)


def side(side: Side, version: str, results: Iterable[CaseResult]) -> SideResult:
    """A side's score: the mean of its cases' scores, a case left out not counted."""
    mine = [r for r in results if r.side is side and r.left_out is None]
    return SideResult(
        side=side,
        version=version,
        score=mean(r.score for r in mine),
        cases=len(mine),
        unscored=sum(1 for r in mine if r.score is None),
    )


def change(active: SideResult, proposed: SideResult, tolerance: float) -> Verdict:
    """The verdict on a change: a regression beyond the tolerance blocks it (ADR-0134 §4)."""
    if active.score is None or proposed.score is None:
        return Verdict.INCOMPLETE
    if proposed.score < active.score - tolerance - 1e-9:
        return Verdict.REGRESSED
    return Verdict.PASSED


def drift(current: SideResult, previous: float | None, tolerance: float) -> Verdict:
    """The verdict on the same version, run again with no change (ADR-0134 §4)."""
    if current.score is None:
        return Verdict.INCOMPLETE
    if previous is None:
        return Verdict.FIRST
    if current.score < previous - tolerance - 1e-9:
        return Verdict.DRIFT
    return Verdict.STEADY


def evaluated(difference: Difference) -> bool:
    """Whether a proposal is held to the cases: it adds, removes or changes a step. A change of
    the autonomy, the triggers or the inputs alone produces what the active version produces."""
    return bool(difference.steps)


def read_inputs(version: ProcessVersion) -> frozenset[str]:
    """The inputs the version's steps read through `$input`."""
    return frozenset(_inputs_in(dict(version.work)))


def personal_inputs(version: ProcessVersion) -> frozenset[str]:
    """The inputs a step's scope names as its subject: personal by declaration (ADR-0130 §2)."""
    found: set[str] = set()
    for work in version.work.values():
        scope = (work or {}).get("scope")
        subject = scope.get("subject") if isinstance(scope, Mapping) else None
        if isinstance(subject, Mapping) and isinstance(subject.get(INPUT), str):
            found.add(subject[INPUT])
    return frozenset(found)


def reduced(
    inputs: Mapping[str, Any], version: ProcessVersion
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """A run's inputs reduced to those the version's steps read, and the names left out."""
    kept = read_inputs(version)
    return (
        {name: value for name, value in inputs.items() if name in kept},
        tuple(sorted(name for name in inputs if name not in kept)),
    )


def _inputs_in(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        named = node.get(INPUT)
        if isinstance(named, str):
            found.append(named.split(".", 1)[0])
        for value in node.values():
            found.extend(_inputs_in(value))
    elif isinstance(node, list | tuple):
        for item in node:
            found.extend(_inputs_in(item))
    return found
