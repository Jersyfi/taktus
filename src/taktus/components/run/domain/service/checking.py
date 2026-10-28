"""The checks of the catalogue, carried out on a step's value before it counts (UC-4.13, ADR-0014,
ADR-0152). Pure: rules over the value and what a check read, never a model.

A step declares its checks (`Step.checks`); the run applies each to the value the step computed,
or to the part of it `checking.select` names. Four kinds judge the value on the spot:

- **bounds** — the value is a number within `minimum` and `maximum`, and its text matches
  `pattern`;
- **reconciliation** — the parts sum to the total read through `source` at the moment of the
  check: a list of numbers, an object of numbers, or one number as its only part;
- **agreement** — the value equals the second system's value read through `source`;
- **recomputation** — the step's rule or statistic, evaluated again over the same inputs, gives
  a value of the same digest.

Two kinds bring a person in. **Approval** holds a value above `threshold` for the role before it
counts. **Sampling** chooses `share` of the results after the fact, by a digest of the run and
the step, so that the same results are chosen for the same runs; the result counts, and a person
of the role judges it afterwards.

Numbers are compared in decimal, from their text: `0.1 + 0.2` reconciles with `0.3`. A check
that cannot be applied — a value that is not a number where one is needed, a reading without the
part it names — fails: a value no check could judge does not count (ADR-0014).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from taktus.shared.v1 import Check, CheckKind

READS = frozenset({CheckKind.RECONCILIATION, CheckKind.AGREEMENT})
"""The kinds that read a source through a connector at the moment of the check."""

JUDGED = frozenset(
    {CheckKind.BOUNDS, CheckKind.RECONCILIATION, CheckKind.AGREEMENT, CheckKind.RECOMPUTATION}
)
"""The kinds a rule decides on the spot; the other two bring a person in."""


@dataclass(frozen=True)
class Finding:
    """One check, applied: whether it passed, and what it compared, in words a person reads in
    the escalation (ADR-0014, "`exact`, written out")."""

    position: int
    """The check's place in the step's declaration, from 1."""
    check: Check
    passed: bool
    compared: str

    def describe(self) -> str:
        verdict = "passed" if self.passed else "failed"
        return f"check {self.position} ({parameters(self.check)}) {verdict}: {self.compared}"


def parameters(check: Check) -> str:
    """The check's kind and its parameters, as declared: what the escalation names."""
    given = check.model_dump(exclude_none=True, mode="json", by_alias=True)
    kind = given.pop("kind")
    given.pop("subject", None)
    if not given:
        return str(kind)
    return f"{kind}: " + ", ".join(f"{key} {value}" for key, value in sorted(given.items()))


def decimal(value: Any) -> Decimal | None:
    """The value as a decimal, from its text; None for anything that is not a finite number. A
    truth value is not a number."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float | str):
        try:
            number = Decimal(str(value).strip())
        except InvalidOperation:
            return None
        return number if number.is_finite() else None
    return None


def text(value: Any) -> str:
    """The value as text: a text as itself, anything else as its JSON."""
    return (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )


def bounds(position: int, check: Check, value: Any) -> Finding:
    said: list[str] = []
    if check.minimum is not None or check.maximum is not None:
        number = decimal(value)
        if number is None:
            return Finding(position, check, False, f"the value {_short(value)} is not a number")
        if check.minimum is not None and number < decimal(check.minimum):  # type: ignore[operator]
            return Finding(
                position, check, False, f"the value {number} is below {_n(check.minimum)}"
            )
        if check.maximum is not None and number > decimal(check.maximum):  # type: ignore[operator]
            return Finding(
                position, check, False, f"the value {number} is above {_n(check.maximum)}"
            )
        said.append(f"the value {number} lies within the bounds")
    if check.pattern is not None:
        if re.search(check.pattern, text(value)) is None:
            return Finding(
                position,
                check,
                False,
                f"the value {_short(value)} does not match the pattern {check.pattern!r}",
            )
        said.append(f"the value matches the pattern {check.pattern!r}")
    return Finding(position, check, True, "; ".join(said))


def parts(value: Any) -> list[Decimal] | None:
    """The parts a reconciliation sums: a list of numbers, an object's numbers, or one number.
    None when any part is not a number."""
    if isinstance(value, Mapping):
        items: Sequence[Any] = list(value.values())
    elif isinstance(value, list | tuple):
        items = value
    else:
        items = [value]
    numbers = [decimal(item) for item in items]
    if not numbers or any(number is None for number in numbers):
        return None
    return [number for number in numbers if number is not None]


def reconciliation(position: int, check: Check, value: Any, total: Any) -> Finding:
    summed = parts(value)
    if summed is None:
        return Finding(position, check, False, f"the parts {_short(value)} are not all numbers")
    expected = decimal(total)
    if expected is None:
        return Finding(
            position,
            check,
            False,
            f"{check.total} read through {check.source} is not a number: {_short(total)}",
        )
    found = sum(summed, Decimal(0))
    if found != expected:
        return Finding(
            position,
            check,
            False,
            f"the parts sum to {found}; {check.total} read through {check.source} is {expected}",
        )
    return Finding(
        position,
        check,
        True,
        f"the parts sum to {found}, which is {check.total} read through {check.source}",
    )


def agreement(position: int, check: Check, value: Any, other: Any) -> Finding:
    if not _same(value, other):
        reference = (
            "the step's own value" if check.reference == "step" else "the second system's value"
        )
        return Finding(
            position,
            check,
            False,
            f"the value {_short(value)} differs from {_short(other)}, which the second system "
            f"holds, read through {check.source}; the reference is {reference}",
        )
    return Finding(
        position,
        check,
        True,
        f"the value {_short(value)} is what the second system holds, read through {check.source}",
    )


def recomputation(position: int, check: Check, first: str, again: str) -> Finding:
    """The digests of the value as the step produced it and as its rule gives it again."""
    if first != again:
        return Finding(
            position,
            check,
            False,
            f"the value's digest is {first[:19]}…, evaluated again over the same inputs it is "
            f"{again[:19]}…",
        )
    return Finding(
        position, check, True, "evaluated again over the same inputs, the value is the same"
    )


def above_threshold(check: Check, value: Any) -> bool | None:
    """Whether an approval check holds the value for a person: above its threshold. None when
    the value is not a number, which no threshold can judge."""
    number = decimal(value)
    if number is None:
        return None
    return number > decimal(check.threshold)  # type: ignore[operator]


def sampled(check: Check, run_id: str, step_id: str) -> bool:
    """Whether a sampling check chooses this step's result: the same answer for the same run and
    step, and over many runs the stated share of them."""
    seed = f"{run_id}\n{step_id}".encode()
    drawn = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") / 2**64
    return drawn < (check.share or 0)


def approval_key(position: int, digest: str) -> str:
    """What stands for an anchor in the identifier of an approval's request: the check and the
    value it approves, so that a confirmation counts for that value only."""
    return f"approval-{position}-{digest.removeprefix('sha256:')[:16]}"


def sample_key(position: int) -> str:
    """What stands for an anchor in the identifier of a sample's request."""
    return f"sample-{position}"


def _same(a: Any, b: Any) -> bool:
    """Two numbers agree by value, whether written as numbers or as decimal text; anything
    else agrees by its text."""
    left, right = decimal(a), decimal(b)
    if left is not None and right is not None:
        return left == right
    return text(a) == text(b)


def _n(value: float) -> str:
    return str(decimal(value))


def _short(value: Any) -> str:
    shown = text(value)
    return shown if len(shown) <= 120 else shown[:117] + "…"
