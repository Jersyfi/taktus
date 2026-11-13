"""Whether a version's exchanges with partners hold to their data contracts (UC-15.3,
ADR-0273 §2). Pure: the version in, findings out.

A step that calls an operation of a capability carrying a partner's data must be named by a
contract. An `import` step carries a check of the shape of what it read whose columns hold every
field the contract requires; an `export` step depends on a step that carries one. A contract
follows an open standard or says why a proprietary format, and one that names a frequency
belongs to a version that expects its runs.

`breach` says which clause of its contract a failed exchange step broke, for the escalation
that brings a person in (ADR-0303). `too_often` says the same of a message that arrived before
the contract's frequency allows one. `propose_mapping` proposes, from a partner's sample
messages, how their fields correspond to the contract's, for a person to confirm; a confirmed
mapping is held by `findings` (ADR-0315).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from taktus.components.process.domain.model.process import MappingDraft
from taktus.shared.v1 import CheckKind, Step

if TYPE_CHECKING:
    from taktus.components.process.domain.model.process import DataContract, ProcessVersion

PARTNER_CAPABILITIES = frozenset({"documents.invoices"})
"""The capabilities whose operations carry a partner's data in an exchange format: incoming
electronic invoices (ADR-0169). One that arrives with a connector is added here."""


def findings(version: ProcessVersion) -> list[str]:
    found: list[str] = []
    named: dict[str, str] = {}
    ids = {step.id for step in version.steps}
    for name, contract in version.contracts.items():
        if (contract.standard is None) == (contract.proprietary is None):
            found.append(
                f"the data contract {name!r} names the open standard it follows, or why a "
                "proprietary format under `proprietary`, and not both"
            )
        if contract.frequency is not None and not (
            version.expected_schedules or version.expect is not None
        ):
            found.append(
                f"the data contract {name!r} expects an exchange every "
                f"{contract.frequency}, and the version expects no run: a missing exchange "
                "would not be noticed (ADR-0107)"
            )
        found.extend(_mapping(name, contract))
        for step_id in contract.steps:
            if step_id not in ids:
                found.append(f"the data contract {name!r} names {step_id!r}, no step of it")
                continue
            if step_id in named:
                found.append(
                    f"the step {step_id!r} is named by the data contracts {named[step_id]!r} "
                    f"and {name!r}; one exchange has one contract"
                )
            named[step_id] = name
            found.extend(_held(version, name, contract, version.step(step_id)))
    for step in version.steps:
        work = version.work.get(step.id) or {}
        operation = work.get("operation")
        if (
            isinstance(operation, str)
            and operation.rsplit(".", 1)[0] in PARTNER_CAPABILITIES
            and step.id not in named
        ):
            found.append(
                f"the step {step.id!r} exchanges data with a partner through {operation}, and "
                "no data contract under `contracts` names it (UC-15.3)"
            )
    return found


def _held(version: ProcessVersion, name: str, contract: DataContract, step: Step) -> list[str]:
    required = set(contract.required)
    if contract.direction == "import":
        if not _covers(step, required):
            return [
                f"the step {step.id!r} imports under the data contract {name!r} and carries no "
                "`source_shape` check whose columns hold every field it requires: "
                + ", ".join(sorted(required))
            ]
        return []
    if not any(_covers(version.step(d), required) for d in step.dependencies):
        return [
            f"the step {step.id!r} exports under the data contract {name!r}, and no step it "
            "depends on checks the document against the fields it requires: "
            + ", ".join(sorted(required))
        ]
    return []


def _covers(step: Step, required: set[str]) -> bool:
    return any(
        check.kind is CheckKind.SOURCE_SHAPE and required <= set(check.columns or ())
        for check in step.checks or ()
    )


def breach(version: ProcessVersion, step_id: str, lacking: Sequence[str]) -> str | None:
    """The clause of a data contract that a failed exchange step breaks, in words (UC-15.3,
    ADR-0303): the contract, its partner and standard, each required field the message lacks
    with the clause that requires it, and who answers for the contract on each side. None where
    no contract names the step, nor an export whose document the step checks. `lacking` is
    what the step's failed check found missing; a field the contract does not require is not
    its breach."""
    named = next(
        ((name, c) for name, c in version.contracts.items() if step_id in c.steps), None
    ) or next(
        (
            (name, c)
            for name, c in version.contracts.items()
            if c.direction == "export"
            and any(step_id in version.step(s).dependencies for s in c.steps)
        ),
        None,
    )
    if named is None:
        return None
    name, contract = named
    after = contract.standard or f"a proprietary format ({contract.proprietary})"
    fields = [f for f in lacking if f in contract.required]
    if fields:
        broken = "; ".join(
            f"the field {f!r} is missing, which the clause `fields.{f}: required` requires"
            for f in fields
        )
    else:
        required = ", ".join(contract.required)
        broken = f"the message does not have the shape the clause `fields` requires: {required}"
    return (
        f"The {contract.direction} breaks the data contract {name!r} with {contract.partner}, "
        f"after {after}: {broken}. Responsible: {contract.responsible.ours} on our side, "
        f"{contract.responsible.theirs} on theirs. Nothing of the message was mapped, "
        "completed or guessed."
    )


def _mapping(name: str, contract: DataContract) -> list[str]:
    """A confirmed mapping maps fields of the contract only, and every field it requires."""
    if contract.mapping is None:
        return []
    fields = {f.name for f in contract.fields}
    found = [
        f"the mapping of the data contract {name!r} maps {field!r}, which is not one of its fields"
        for field in sorted(set(contract.mapping) - fields)
    ]
    found.extend(
        f"the mapping of the data contract {name!r} does not say where the partner's message "
        f"carries {field!r}, which the contract requires"
        for field in contract.required
        if field not in contract.mapping
    )
    return found


def too_often(version: ProcessVersion, step_id: str, since: timedelta) -> str | None:
    """The clause a message breaks that an import step received `since` after the one before,
    where its contract expects one every `frequency` and `since` is shorter (ADR-0315). None
    where no import contract with a frequency names the step, or the message is not early."""
    named = next(
        (
            (n, c)
            for n, c in version.contracts.items()
            if c.direction == "import" and step_id in c.steps and c.frequency is not None
        ),
        None,
    )
    if named is None:
        return None
    name, contract = named
    assert contract.frequency is not None  # noqa: S101 — selected above
    if since >= contract.frequency:
        return None
    return (
        f"The import breaks the data contract {name!r} with {contract.partner}: a message "
        f"arrived {_span(since)} after the one before, and the clause `frequency` expects one "
        f"every {_span(contract.frequency)}. Responsible: {contract.responsible.ours} on our "
        f"side, {contract.responsible.theirs} on theirs. Nothing of the message was mapped, "
        "completed or guessed."
    )


def propose_mapping(contract: DataContract, samples: Sequence[Mapping[str, Any]]) -> MappingDraft:
    """How the partner's sample messages correspond to the contract's fields, proposed by rule:
    a field takes the path every sample carries whose last name equals the field's, letter for
    letter or once case and separators are set aside. A field two such paths match is left for
    the person to choose; one none matches is asked for (ADR-0315)."""
    paths: set[str] | None = None
    for sample in samples:
        found = set(_paths(sample))
        paths = found if paths is None else paths & found
    carried = sorted(paths or ())
    proposed: dict[str, str] = {}
    why: dict[str, str] = {}
    ambiguous: dict[str, tuple[str, ...]] = {}
    unmatched: list[str] = []
    for field in contract.fields:
        exact = [p for p in carried if p.rsplit(".", 1)[-1] == field.name]
        loose = [p for p in carried if _plain(p.rsplit(".", 1)[-1]) == _plain(field.name)]
        chosen = exact if exact else loose
        if len(chosen) == 1:
            proposed[field.name] = chosen[0]
            why[field.name] = (
                "the same name"
                if exact
                else "the same name, once case and separators are set aside"
            )
        elif chosen:
            ambiguous[field.name] = tuple(chosen)
        else:
            unmatched.append(field.name)
    taken = set(proposed.values()) | {p for c in ambiguous.values() for p in c}
    unused = tuple(
        p for p in carried if p not in taken and not any(q.startswith(p + ".") for q in carried)
    )
    lines = [f"{field} ← {path}" for field, path in proposed.items()]
    question = (
        f"From {len(samples)} sample message(s) of {contract.partner}, the fields correspond "
        "like this: " + ("; ".join(lines) if lines else "no field could be matched") + "."
    )
    if ambiguous:
        question += " Choose the path for: " + ", ".join(sorted(ambiguous)) + "."
    if unmatched:
        question += (
            " Name the path, or say the partner does not send: " + ", ".join(unmatched) + "."
        )
    question += (
        " Is this right? Nothing is applied until a version whose contract carries the mapping "
        "you confirm is registered."
    )
    return MappingDraft(
        proposed=proposed,
        why=why,
        ambiguous=ambiguous,
        unmatched=tuple(unmatched),
        unused=unused,
        question=question,
    )


def _paths(value: Any, prefix: str = "") -> list[str]:
    """Every dotted path of an object, its nested objects' too; a list is a leaf."""
    if not isinstance(value, Mapping):
        return []
    found: list[str] = []
    for key, inner in value.items():
        path = f"{prefix}{key}"
        found.append(path)
        found.extend(_paths(inner, path + "."))
    return found


def _plain(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _span(span: timedelta) -> str:
    """A time in its largest unit, to a tenth: `3h`, `1.5d`, `40s`."""
    seconds = span.total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if seconds >= size:
            return f"{round(seconds / size, 1):g}{unit}"
    return f"{round(seconds):g}s"
