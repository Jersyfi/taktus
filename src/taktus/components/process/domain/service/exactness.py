"""How a step becomes exact, and what the process version says about it (UC-4.13, UC-6.9).

Two rules over a process version, both evaluated when a bundle registers (ADR-0082):

- `findings`: a step classed `exact` declares at least one check from the catalogue; the
  finding for one that declares none names the catalogue, row by row, with what each row covers,
  what it does not cover and what it needs — the content of the conversation UC-4.13 asks for,
  as a validation finding for a person who writes the bundle by hand. A recomputation is
  declared on a step whose method gives the same result again: `rule` or `statistics`.
- `statement`: the exactness statement, generated from the steps' classes and checks. Every
  sentence is its catalogue row's, filled in with the check's own parameters; nothing else is
  said about a check. A rule, never a model, writes it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from taktus.components.process.domain.model.exactness import (
    CATALOGUE,
    NOT_YET_MEASURED,
    ExactnessStatement,
)
from taktus.shared.v1 import (
    EXACT_ADMISSIBLE,
    Check,
    CheckKind,
    ExactnessClass,
    Reference,
    Step,
)


def findings(steps: Sequence[Step]) -> list[str]:
    """What refuses the version: an exact step without a check, a recomputation that cannot
    give the same result again."""
    found: list[str] = []
    for step in steps:
        if step.exactness is ExactnessClass.EXACT and not step.checks:
            found.append(
                f"step {step.id!r} is classed exact and declares no check: `exact` is a claim "
                "that a machine check makes the value right, and the check has to exist "
                "(ADR-0014, UC-4.13). Declare one under `checks` from the catalogue — "
                + "; ".join(
                    f"{kind.value} ({row.name}): covers {row.covers}; does not cover "
                    f"{row.does_not_cover}; needs {row.needs}"
                    for kind, row in CATALOGUE.items()
                )
                + ". Where none fits, the step is not exact: it goes to a person (`human`), "
                "or to `sourced` with the check that does fit"
            )
        for check in step.checks or ():
            if check.kind is CheckKind.RECOMPUTATION and step.method not in EXACT_ADMISSIBLE:
                found.append(
                    f"step {step.id!r} declares a recomputation, but a {step.method} step does "
                    "not give the same result again; recomputation is a check of a step on "
                    "rule or statistics"
                )
    return found


def statement(process_version: str, name: str, steps: Iterable[Step]) -> ExactnessStatement:
    """The exactness statement of a version, from its steps in declared order. Raises
    `InvalidStatement` where a statement could not be complete or would say "guaranteed"."""
    applies: list[str] = []
    covers: list[str] = []
    not_covered: list[str] = []
    residual: list[str] = []
    producing = [(step, step.exactness) for step in steps if step.exactness is not None]
    for step, cls in producing:
        where = f"`{step.id}` ({cls.value})"
        checks = step.checks or ()
        if not checks:
            applies.append(f"{where}: no check declared.")
            not_covered.append(
                f"{where}: the step declares no check, so no wrong result of it is found by one."
            )
            residual.append(f"{where}: every wrong result slips through; no check applies to it.")
            continue
        applies.append(f"{where}: " + "; ".join(_applies(check) for check in checks) + ".")
        covers.extend(f"{where}: {_covers(step, check)}" for check in checks)
        not_covered.extend(f"{where}: {_does_not_cover(step, check)}" for check in checks)
        residual.append(
            f"{where}: a wrong result slips through only where every check misses it at once — "
            + "; and ".join(_slips(step, check) for check in checks)
            + "."
        )
    if not producing:
        applies.append("No step of this process produces a result (ADR-0018): no check applies.")
        not_covered.append(
            "What a person decides in a `human` step and what a `wait` step passes on: neither "
            "is a result a check applies to (ADR-0018)."
        )
        residual.append("Whatever a person decides wrongly, or a wait passes on wrongly.")
    if not covers:
        covers.append("Nothing: no step of this process declares a check.")
    residual.append(NOT_YET_MEASURED)
    return ExactnessStatement(
        process_version=process_version,
        name=name,
        applies=tuple(applies),
        covers=tuple(covers),
        does_not_cover=tuple(not_covered),
        residual=tuple(residual),
    )


def _subject(check: Check) -> str:
    return check.subject or "the result"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _bounds(check: Check) -> str:
    said: list[str] = []
    if check.minimum is not None and check.maximum is not None:
        said.append(f"lies between {_number(check.minimum)} and {_number(check.maximum)}")
    elif check.minimum is not None:
        said.append(f"is at least {_number(check.minimum)}")
    elif check.maximum is not None:
        said.append(f"is at most {_number(check.maximum)}")
    if check.pattern is not None:
        said.append(f"matches the pattern `{check.pattern}`")
    return " and ".join(said)


def _share(check: Check) -> str:
    share = check.share or 0  # the row requires it
    return f"{_number(round(share * 100, 4))} %"


def _applies(check: Check) -> str:
    row = CATALOGUE[check.kind].name
    match check.kind:
        case CheckKind.RECONCILIATION:
            return f"{row} — {check.total}, read through `{check.source}`"
        case CheckKind.AGREEMENT:
            return f"{row} — read through `{check.source}`, reference: {_reference(check)}"
        case CheckKind.BOUNDS:
            return f"{row} — {_subject(check)} {_bounds(check)}"
        case CheckKind.APPROVAL:
            return f"{row} — above {_number(check.threshold or 0)}, by the role `{check.role}`"
        case CheckKind.SAMPLING:
            return f"{row} — {_share(check)} of results, by the role `{check.role}`"
        case CheckKind.RECOMPUTATION:
            return f"{row} — over the inputs the provenance record names"


def _reference(check: Check) -> str:
    if check.reference is Reference.STEP:
        return "the step's own value"
    return "the second system's value"


def _covers(step: Step, check: Check) -> str:
    subject = _capital(_subject(check))
    match check.kind:
        case CheckKind.RECONCILIATION:
            return (
                f"{subject} is reconciled against {check.total}, read through `{check.source}` "
                "at the moment of the check: the parts must sum to it."
            )
        case CheckKind.AGREEMENT:
            return (
                f"{subject} must equal what the second system, read through `{check.source}`, "
                f"holds for the same thing; where they differ, {_reference(check)} is the "
                "reference."
            )
        case CheckKind.BOUNDS:
            return f"{subject} counts only where it {_bounds(check)}."
        case CheckKind.APPROVAL:
            return (
                f"{subject} above {_number(check.threshold or 0)} is confirmed by a person in "
                f"the role `{check.role}` before it counts."
            )
        case CheckKind.SAMPLING:
            return (
                f"{subject} is checked after the fact in {_share(check)} of the results, by a "
                f"person in the role `{check.role}`, and the error rate is measured."
            )
        case CheckKind.RECOMPUTATION:
            return (
                f"{subject} is what the step's {step.method} gives again over the inputs its "
                "provenance record names: a result that does not follow from its recorded "
                "inputs is found."
            )


def _does_not_cover(step: Step, check: Check) -> str:
    subject = _subject(check)
    match check.kind:
        case CheckKind.RECONCILIATION:
            return (
                f"A part of {subject} wrong by exactly what another part is wrong by in the "
                f"other direction passes, and so does {check.total} where it is itself wrong."
            )
        case CheckKind.AGREEMENT:
            return (
                f"{_capital(subject)} wrong in both systems the same way passes, and so does "
                "any value where the second system is fed from the first."
            )
        case CheckKind.BOUNDS:
            return f"A wrong value of {subject} that {_bounds(check)} passes."
        case CheckKind.APPROVAL:
            threshold = _number(check.threshold or 0)
            return (
                f"A wrong value of {subject} at or below {threshold} counts unconfirmed, and so "
                "does a value a person confirms without looking."
            )
        case CheckKind.SAMPLING:
            return (
                f"A wrong value of {subject} that is not in the sample is not found by this check."
            )
        case CheckKind.RECOMPUTATION:
            return (
                f"{_capital(subject)} computed from inputs that were themselves wrong passes, "
                f"and so does a {step.method} that computes the wrong thing the same way every "
                "time."
            )


def _slips(step: Step, check: Check) -> str:
    match check.kind:
        case CheckKind.RECONCILIATION:
            return f"an error another part offsets, or {check.total} itself wrong"
        case CheckKind.AGREEMENT:
            return "a value wrong in both systems alike, or a second system fed from the first"
        case CheckKind.BOUNDS:
            return f"a wrong value that {_bounds(check)}"
        case CheckKind.APPROVAL:
            return (
                f"a wrong value at or below {_number(check.threshold or 0)}, or a confirmation "
                "given without looking"
            )
        case CheckKind.SAMPLING:
            return "a wrong value outside the sample"
        case CheckKind.RECOMPUTATION:
            return f"wrong inputs, or a {step.method} that computes the wrong thing"
