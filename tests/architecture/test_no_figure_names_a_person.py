"""Principle 14 in the data model: no figure names a person (ADR-0015, UC-6.4, UC-13.5, #94).

Principle 14 forbids any metric that appraises a named person, and says such a feature is
unbuildable, not switched off. This module holds every value type of the core — components,
ports, the shared kernel, `wire` — and every table of the database to that rule.

Two words carry the rule.

- A **figure** is a quantity: a field whose type is a number or a duration, held directly or in
  a value the type contains.
- A field **names a person** when its name says it holds an identity: one of `PERSON_WORDS`, a
  name ending in `_by`, or a name containing `person` or `people`.

A type or table that names a person and holds a figure is refused, except in two shapes, each
listed below with its reason:

- **One act** (`ACTS`): a record of one act or a command for one, naming who acts as the audit
  requires (ADR-0006, ADR-0043 §7), with that act's own quantities. It holds no total over
  several acts: a field named for a count, a sum, a median, a share, a rate, a rank or a score
  is refused in it.
- **One's own** (`OWN`): a read computed for the person reading it. Its only person field is
  `reader`, and the test named beside it proves that nobody else reads it under that name
  (ADR-0015, protective rule).

Anywhere, a field that groups by person — `by_person`, `per_identity` — is refused. A listed act
inside another type is held to the rule on its own, so the type around it is not read as a
figure of the person who acted. A listed type or table that no longer exists, or no longer names
a person, fails too, so the lists say what is, not what was.

Where it ends: a person is recognised by a field's name, so an identity kept under an unrelated
name is not seen; a mapping keyed by identities under a neutral name is not seen either. Records
of single acts stay readable under the visibility predicate, and whoever reads them can compute
a person's times by hand; the data model never does it for them (ADR-0015, ADR-0043).
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import importlib
import inspect
import pkgutil
import typing
from collections.abc import Iterator
from types import UnionType

import pytest
import sqlalchemy as sa
from pydantic import BaseModel

from taktus.adapters.driven.postgres._schema import metadata
from taktus.shared.v1 import Value

CORE = ("components", "ports", "shared", "wire")

PERSON_WORDS = frozenset(
    {
        "actor",
        "assignee",
        "author",
        "by",
        "employee",
        "employees",
        "identities",
        "identity",
        "member",
        "members",
        "owner",
        "reader",
        "user_id",
        "users",
        "who",
    }
)
"""Field names that hold an identity. `decider` is not one: it is the role a request is
addressed to (ADR-0042)."""

TOTAL_WORDS = frozenset(
    {
        "average",
        "count",
        "leaderboard",
        "mean",
        "median",
        "percentile",
        "rank",
        "ranking",
        "rate",
        "score",
        "share",
        "sum",
        "sums",
        "total",
        "totals",
    }
)
"""Words of a field that totals, compares or orders several acts, matched as `_`-separated
parts of its name."""

QUANTITY = (int, float, decimal.Decimal, datetime.timedelta)
QUANTITY_COLUMNS = (sa.Integer, sa.Float, sa.Numeric, sa.Interval)

ACT = "one act: who acts, as the audit requires, with that act's own quantities"

ACTS: dict[str, str] = {
    "taktus.components.run.domain.model.run.Run": (
        f"{ACT}: the identity a run acts for, and its budget, margin and level"
    ),
    "taktus.components.run.domain.model.run.StepRun": (
        f"{ACT}: who confirmed the step (ADR-0039), and its attempt and position"
    ),
    "taktus.components.run.domain.model.run.Anchoring": (
        f"{ACT}: who decided an anchored step (ADR-0042), and the round of its requests"
    ),
    "taktus.components.run.application.service.execute_run.StartRun": (
        f"{ACT}: the command that starts a run, with who starts it"
    ),
    "taktus.components.run.application.service.execute_run.ResumeRun": (
        f"{ACT}: the command that resumes a run, with who resumes it"
    ),
    "taktus.components.run.application.service.execute_run.ConfirmSteps": (
        f"{ACT}: the command that confirms steps, with who confirms them"
    ),
    "taktus.components.run.application.service.execute_run.DecideSteps": (
        f"{ACT}: the command that applies a verdict, with who applies it"
    ),
    "taktus.components.run.application.service.runner.RunnerOptions": (
        f"{ACT}: the identity a runner acts as, and how many runs it carries"
    ),
    "taktus.components.process.domain.model.process.ProcessVersion": (
        f"{ACT}: who wrote a version, and its level"
    ),
    "taktus.components.process.domain.model.trigger_state.Firing": (
        f"{ACT}: one firing of a trigger, and who fired it by hand"
    ),
    "taktus.components.catalog.domain.model.maturity.ConformanceResult": (
        f"{ACT}: one conformance run, and who started it"
    ),
    "taktus.components.reporting.domain.model.report.Happened": (
        f"{ACT}: one entry of a report's history, and who acted"
    ),
    "taktus.components.reporting.domain.model.report.Reading": (
        f"{ACT}: one answer read back, and who gave it"
    ),
    "taktus.components.reporting.domain.model.report.Filed": (
        f"{ACT}: one answer filed, and who gave it"
    ),
    "taktus.ports.connector.CallContext": (
        f"{ACT}: one call of a connector, for whom it acts, and its attempt"
    ),
    "taktus.ports.ledger.Fact": f"{ACT}: one ledger entry before it is chained",
    "taktus.shared.v1.ledger_entry.LedgerEntry": (
        f"{ACT}: one ledger entry, who acted, and what that one step consumed (ADR-0006)"
    ),
}
"""Every type that is one act and names a person: beside a quantity, or held inside a type
that has one."""

ACT_TABLES: dict[str, str] = {
    "run": "the table of `Run`",
    "step_run": "the table of `StepRun`",
    "plan": f"{ACT}: who commissioned a plan, and its level",
    "process_version": "the table of `ProcessVersion`",
    "job": f"{ACT}: one job and the runner that claimed it, a process and not a person",
}
"""Every table that names a person beside a quantity, as one act."""

OWN: dict[str, str] = {
    "taktus.components.decision.domain.service.response_times.ResponseTimes": (
        "tests/governance/test_anchors.py::"
        "test_another_identity_cannot_read_a_decider_s_response_time_under_their_name"
    ),
}
"""Every read computed for its reader, with the test that proves nobody else reads it."""


# --- discovery ---------------------------------------------------------------------------------


def core_types() -> dict[str, type]:
    found: dict[str, type] = {}
    for area in CORE:
        package = importlib.import_module(f"taktus.{area}")
        modules = [package]
        modules += [
            importlib.import_module(info.name)
            for info in pkgutil.walk_packages(package.__path__, f"taktus.{area}.")
        ]
        for module in modules:
            for _, kind in inspect.getmembers(module, inspect.isclass):
                if kind.__module__ != module.__name__:
                    continue
                if issubclass(kind, BaseModel) or dataclasses.is_dataclass(kind):
                    found[f"{kind.__module__}.{kind.__qualname__}"] = kind
    return found


def fields(kind: type) -> dict[str, object]:
    if issubclass(kind, BaseModel):
        return {name: info.annotation for name, info in kind.model_fields.items()}
    hints = typing.get_type_hints(kind)
    return {f.name: hints.get(f.name, f.type) for f in dataclasses.fields(kind)}


def leaves(annotation: object) -> Iterator[object]:
    """The plain types an annotation is made of: through unions, containers, aliases."""
    if isinstance(annotation, typing.TypeAliasType):
        yield from leaves(annotation.__value__)
        return
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        yield from leaves(typing.get_args(annotation)[0])
        return
    if origin is None:
        yield annotation
        return
    if origin not in (typing.Union, UnionType, typing.Literal):
        yield origin
    if origin is typing.Literal:
        return
    for argument in typing.get_args(annotation):
        if argument is not Ellipsis:
            yield from leaves(argument)


def is_quantity(leaf: object) -> bool:
    return isinstance(leaf, type) and issubclass(leaf, QUANTITY) and leaf is not bool


def is_value(leaf: object) -> bool:
    return isinstance(leaf, type) and (
        issubclass(leaf, BaseModel) or dataclasses.is_dataclass(leaf)
    )


def names_person(name: str) -> bool:
    return name in PERSON_WORDS or name.endswith("_by") or "person" in name or "people" in name


def groups_by_person(name: str) -> bool:
    for prefix in ("by_", "per_"):
        if name.startswith(prefix) and names_person(name.removeprefix(prefix)):
            return True
    return False


def is_total(name: str) -> bool:
    return bool(set(name.split("_")) & TOTAL_WORDS)


def qualified(kind: type) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def nested(kind: type, seen: set[type] | None = None) -> Iterator[type]:
    """The type itself and every value type it contains, once each. A listed act contained in
    another type is held to the rule on its own, so the descent does not enter it: who acted in
    a record is not the subject of what the type around it counts."""
    seen = set() if seen is None else seen
    if kind in seen:
        return
    seen.add(kind)
    yield kind
    for annotation in fields(kind).values():
        for leaf in leaves(annotation):
            if is_value(leaf):
                assert isinstance(leaf, type)
                if qualified(leaf) not in ACTS:
                    yield from nested(leaf, seen)


def quantities(kind: type) -> list[str]:
    """Every field holding a quantity, in the type or in a value it contains."""
    return [
        f"{inner.__qualname__}.{name}"
        for inner in nested(kind)
        for name, annotation in fields(inner).items()
        if any(is_quantity(leaf) for leaf in leaves(annotation))
    ]


def persons(kind: type) -> list[str]:
    """Every field naming a person, in the type or in a value it contains."""
    return [
        f"{inner.__qualname__}.{name}"
        for inner in nested(kind)
        for name in fields(inner)
        if names_person(name)
    ]


def verdict(name: str, kind: type) -> str | None:
    """Why `kind` breaks the rule, or None."""
    for inner in nested(kind):
        grouped = [f for f in fields(inner) if groups_by_person(f)]
        if grouped:
            return f"{inner.__qualname__} groups by person: {grouped}"
    who = persons(kind)
    held = quantities(kind)
    if name in OWN:
        if who != [f"{kind.__qualname__}.reader"]:
            return f"a read of one's own names only its reader; it names {who}"
        return None
    if not who or not held:
        return None
    if name in ACTS:
        totals = [
            f"{inner.__qualname__}.{f}"
            for inner in nested(kind)
            for f in fields(inner)
            if is_total(f)
        ]
        if totals:
            return f"one act holds no total over several, and this one names {who} beside {totals}"
        return None
    return (
        f"names a person ({who}) beside a figure ({held}); principle 14 forbids it. A record of "
        "one act belongs in ACTS with its reason, a read of one's own in OWN with its test"
    )


TYPES = core_types()


# --- the rule ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TYPES))
def test_no_type_of_the_core_holds_a_figure_under_a_persons_name(name: str) -> None:
    assert verdict(name, TYPES[name]) is None, f"{name}: {verdict(name, TYPES[name])}"


@pytest.mark.parametrize("table", sorted(metadata.tables))
def test_no_table_holds_a_figure_under_a_persons_name(table: str) -> None:
    columns = metadata.tables[table].columns
    who = [c.name for c in columns if names_person(c.name)]
    held = [c.name for c in columns if isinstance(c.type, QUANTITY_COLUMNS)]
    grouped = [c.name for c in columns if groups_by_person(c.name)]
    assert not grouped, f"{table} groups by person: {grouped}"
    if not who or not held:
        return
    assert table in ACT_TABLES, (
        f"{table} names a person ({who}) beside a figure ({held}); principle 14 forbids it"
    )
    totals = [c.name for c in columns if is_total(c.name)]
    assert not totals, f"{table} is one act and holds a total: {totals}"


def test_every_listed_type_still_names_a_person() -> None:
    for name in (*ACTS, *OWN):
        assert name in TYPES, f"{name} is listed and no longer exists"
        assert persons(TYPES[name]), f"{name} is listed and names no person"
    for name in OWN:
        assert quantities(TYPES[name]), f"{name} is listed and holds no figure"
    for table in ACT_TABLES:
        assert table in metadata.tables, f"table {table} is listed and no longer exists"
        columns = metadata.tables[table].columns
        assert any(names_person(c.name) for c in columns), f"table {table} needs no listing"
        assert any(isinstance(c.type, QUANTITY_COLUMNS) for c in columns), table


def test_every_read_of_ones_own_names_the_test_that_proves_it() -> None:
    """The listing is a claim; the named test is its proof, and it must exist."""
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    for name, node in OWN.items():
        path, function = node.split("::")
        source = (root / path).read_text(encoding="utf-8")
        assert f"def {function}(" in source, f"{name}: {node} does not exist"


# --- the rule bites ----------------------------------------------------------------------------


class _Leaderboard(Value):
    person: str
    seconds: float


class _Line(Value):
    identity: str
    decisions: int


class _Board(Value):
    lines: tuple[_Line, ...]


class _Grouped(Value):
    by_person: dict[str, float]


class _Tally(Value):
    actor: str
    count: int


class _Mine(Value):
    reader: str
    lines: tuple[_Line, ...]


def test_the_rule_refuses_a_figure_under_a_persons_name() -> None:
    assert verdict("x._Leaderboard", _Leaderboard) is not None
    assert verdict("x._Line", _Line) is not None
    assert verdict("x._Grouped", _Grouped) is not None, "a mapping by person"
    assert verdict("x._Board", _Board) is not None, "a person in a contained value"
    assert verdict("x.Plain", Value) is None


def test_a_listing_admits_one_act_without_a_total_and_ones_own_without_another_person() -> None:
    ACTS["x._Tally"] = ACT
    OWN["x._Mine"] = "tests/architecture/test_no_figure_names_a_person.py::x"
    try:
        assert verdict("x._Tally", _Tally) is not None, "one act holds no count"
        assert verdict("x._Mine", _Mine) is not None, "its lines name another person"
    finally:
        del ACTS["x._Tally"], OWN["x._Mine"]
