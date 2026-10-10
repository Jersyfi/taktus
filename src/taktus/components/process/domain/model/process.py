"""Process, process version, edge, trigger and service level (control-plane.md §4)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from pydantic import Field, model_validator

from taktus.components.process.domain.model.errors import InvalidProcess
from taktus.components.process.domain.model.event import (
    KINDS,
    Condition,
    Event,
    FilterValue,
    holds,
)
from taktus.components.process.domain.service import schedule
from taktus.components.process.domain.service.autonomy import actions_used
from taktus.components.process.domain.service.validation import topological_order, validate_graph
from taktus.shared.v1 import Autonomy, AutonomyLevel, ExactnessClass, Step, StepId, Value

# What a step does when it runs — the task for a worker, the rule to evaluate, what to wait for.
# Its shape belongs to the process bundle format, which arrives at 0.3.0 (ADR-0011,
# docs/roadmap.md); until then it is carried as data and interpreted by the component that
# executes it. That is why it is not typed here.
type Work = Mapping[str, Any]

STRICTNESS = (
    ExactnessClass.EXACT,
    ExactnessClass.SOURCED,
    ExactnessClass.TOLERANT,
    ExactnessClass.FREE,
)


class InputDeclaration(Value):
    """One input a run needs: what it is, and an example a test can run the bundle with."""

    description: str = Field(min_length=1)
    # An example value of whatever JSON shape the input has.
    example: Any


class Process(Value):
    """A named process. The version that runs is `active_version`; the versions are bundles."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(min_length=1)
    description: str | None = None
    active_version: str | None = None
    activated_by: str | None = Field(default=None, min_length=1)
    """The identity that registered the active version: whom its schedule triggers act for
    (ADR-0040). None for a version registered without one, whose triggers do not fire."""
    activated_at: datetime | None = None
    """When the active version was registered. An event received before it starts nothing
    (ADR-0048 §6); None for a version registered before this was recorded, whose event
    triggers start nothing until it is registered again."""


class Edge(Value):
    """A dependency: `to_step` starts only after `from_step` has finished."""

    from_step: StepId
    to_step: StepId


class Each(Value):
    """One run per item of a list that a connector reads when the trigger fires. Each run is
    given its item as the input `input`. The operation must be declared `read`. The list is
    the part of its output that `select` names, a dotted path. `field`, when given, is a
    dotted path that picks the value out of each item (ADR-0035)."""

    input: str = Field(min_length=1)
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    select: str = Field(min_length=1)
    field: str | None = Field(default=None, min_length=1)

    @property
    def capability(self) -> str:
        """The capability the operation is named by: every segment but the last."""
        return self.operation.rsplit(".", 1)[0]


class Trigger(Value):
    """What starts a run: a schedule or an event. A process without triggers starts by hand.

    A schedule trigger gives its runs their inputs: fixed values in `inputs`, and one run per
    item of a list in `each`. Together they give every input the process declares, or the
    version is refused: a scheduled run has nobody to ask (ADR-0035).

    An event trigger (`contracts/events/v1` §3) names a kind of the catalogue, a `filter` over
    the event's context, a `condition` on the instance, and gives its run fixed values in
    `inputs` and context fields of the event in `from_event`. What it names is checked against
    the catalogue when the version is registered, with every finding at once (ADR-0048 §7)."""

    schedule: str | None = Field(default=None, min_length=1)
    event: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]*$")
    filter: Mapping[str, FilterValue] | None = None
    condition: str | None = Field(default=None, min_length=1)
    inputs: Mapping[str, Any] | None = None
    each: Each | None = None
    from_event: Mapping[str, str] | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Trigger:
        if (self.schedule is None) == (self.event is None):
            raise ValueError("a trigger names either a schedule or an event")
        if self.schedule is not None:
            schedule.parse(self.schedule)  # an InvalidSchedule is a ValueError and says why
            if self.filter is not None or self.condition is not None:
                raise ValueError("`filter` and `condition` belong to an event trigger")
            if self.from_event is not None:
                raise ValueError("`from_event` belongs to an event trigger")
        elif self.each is not None:
            raise ValueError("`each` belongs to a schedule trigger")
        if self.each is not None and self.each.input in (self.inputs or {}):
            raise ValueError(
                f"the input {self.each.input!r} is given twice: in `inputs` and `each`"
            )
        twice = sorted(set(self.inputs or {}) & set(self.from_event or {}))
        if twice:
            raise ValueError(
                f"the input(s) {', '.join(twice)} given twice: in `inputs` and `from_event`"
            )
        if self.filter is not None:
            if not self.filter:
                raise ValueError("an empty `filter` filters nothing; leave it out")
            empty = sorted(k for k, v in self.filter.items() if isinstance(v, tuple) and not v)
            if empty:
                raise ValueError(f"the filter names no value for {', '.join(empty)}")
        return self

    def findings(self) -> list[str]:
        """What the events contract refuses in this event trigger: a kind outside the
        catalogue, a filter field its kind does not carry, a condition outside the list, an
        input taken from a field its kind does not require. Empty for a schedule trigger."""
        if self.event is None:
            return []
        kind = Event.of(self.event)
        if kind is None:
            return [
                f"the event trigger names {self.event!r}, which is not a kind of the events "
                "contract's catalogue (contracts/events/v1 §2)"
            ]
        fields = KINDS[kind]
        found: list[str] = []
        unknown = sorted(set(self.filter or {}) - fields.known)
        if unknown:
            found.append(
                f"the event trigger {self.event!r} filters on {', '.join(unknown)}, which an "
                "event of that kind does not carry"
            )
        if self.condition is not None and self.condition not in {c.value for c in Condition}:
            found.append(
                f"the event trigger {self.event!r} names the condition {self.condition!r}, "
                "which is not one of the events contract's (contracts/events/v1 §4)"
            )
        loose = sorted(
            f"{name} <- {field}"
            for name, field in (self.from_event or {}).items()
            if field not in fields.required
        )
        if loose:
            found.append(
                f"the event trigger {self.event!r} takes {', '.join(loose)}, a field an event "
                "of that kind does not always carry; a run would start without the input"
            )
        return found

    @property
    def given(self) -> frozenset[str]:
        """The names of the inputs a run started by this trigger is given."""
        names = set(self.inputs or {}) | set(self.from_event or {})
        if self.each is not None:
            names.add(self.each.input)
        return frozenset(names)

    @property
    def key(self) -> str:
        """What identifies the trigger across versions of its process: the digest of what it
        does. A new version with the same trigger keeps the slot it last fired for. A changed
        trigger is a new one."""
        canonical = json.dumps(self.document(), ensure_ascii=False, sort_keys=True)
        return "trg_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


class Slo(Value):
    """The service level a process promises: how fresh its result is, how long a run may take."""

    freshness: timedelta | None = None
    latency: timedelta | None = None


class ProcessVersion(Value):
    """One version of a process: the graph, its triggers and service level, and who changed
    what and why. Every invariant of the graph is checked here; an instance is valid or does
    not exist."""

    process_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1)
    autonomy: Autonomy
    """The level the process runs at, why, and what is missing to go higher (ADR-0026). A
    version without a reason does not exist."""
    steps: tuple[Step, ...] = Field(min_length=1)
    triggers: tuple[Trigger, ...] = ()
    slo: Slo | None = None
    work: Mapping[StepId, Work] = Field(default_factory=dict)
    limits: Work | None = None
    inputs: Mapping[str, InputDeclaration] = Field(default_factory=dict)
    """What a run of this version is given when it starts, by name: what `$input` references
    in the work resolve to. A run that lacks one is refused before anything runs."""
    author: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _valid_graph(self) -> ProcessVersion:
        findings = validate_graph(self.steps)
        ids = {step.id for step in self.steps}
        findings.extend(
            f"work is given for {step_id!r}, which is not a step of this process"
            for step_id in self.work
            if step_id not in ids
        )
        used = actions_used(self.steps, self.work)
        findings.extend(
            f"the autonomy statement sets a level for the action {action!r}, which no step of "
            "this process uses: the level would never apply (ADR-0039)"
            for action in sorted(set(self.autonomy.action_levels) - used)
        )
        for trigger in self.triggers:
            findings.extend(trigger.findings())
            if trigger.schedule is not None:
                named, where = f"the schedule trigger {trigger.schedule!r}", "`inputs` or `each`"
                nobody = "a scheduled run has nobody to ask"
            else:
                named, where = f"the event trigger {trigger.event!r}", "`inputs` or `from_event`"
                nobody = "a run started by an event has nobody to ask"
            missing = sorted(set(self.inputs) - trigger.given)
            unknown = sorted(trigger.given - set(self.inputs))
            if missing:
                findings.append(
                    f"{named} gives no value for the input(s) {', '.join(missing)}; {nobody}, "
                    f"so the trigger names them in {where}"
                )
            if unknown:
                findings.append(
                    f"{named} gives {', '.join(unknown)}, which the process does not declare "
                    "under `inputs`"
                )
        if findings:
            raise InvalidProcess(tuple(findings))
        return self

    @property
    def ref(self) -> str:
        """How the ledger names this version."""
        return f"{self.process_id}@{self.version}"

    @property
    def autonomy_level(self) -> AutonomyLevel:
        """The level alone, for the plan and the run, which carry no reason of their own."""
        return self.autonomy.level

    @property
    def id(self) -> str:
        """The repository key: a version is identified by its process and its version."""
        return self.ref

    @property
    def edges(self) -> tuple[Edge, ...]:
        return tuple(
            Edge(from_step=dependency, to_step=step.id)
            for step in self.steps
            for dependency in step.dependencies
        )

    @property
    def exactness(self) -> ExactnessClass | None:
        """The class of the strictest result the process produces; None when it produces none."""
        classes = [step.exactness for step in self.steps if step.exactness is not None]
        if not classes:
            return None
        return min(classes, key=STRICTNESS.index)

    def step(self, step_id: StepId) -> Step:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def ordered(self) -> tuple[Step, ...]:
        """The steps in execution order: every dependency first, ties in declared order."""
        return topological_order(self.steps)

    def reacting_to(self, event: Event) -> Trigger | None:
        """The first event trigger, in declared order, whose kind is the event's and whose
        filter holds for it; None when none does. A process starts once per event, with the
        inputs of this trigger (ADR-0048 §5). A rule over the event alone (§2)."""
        for trigger in self.triggers:
            if trigger.event == event.kind.value and holds(trigger.filter, event):
                return trigger
        return None

    def given_by(self, trigger: Trigger, event: Event) -> dict[str, Any]:
        """The inputs a run this event trigger starts is given: the fixed values, and the
        event's context fields named in `from_event`. An event carries identifiers as strings;
        where the input's declared example is an integer, a string of decimal digits is given
        as that integer (`contracts/events/v1` §3)."""
        inputs = dict(trigger.inputs or {})
        for name, field in (trigger.from_event or {}).items():
            value = event.context[field]
            declared = self.inputs.get(name)
            example = None if declared is None else declared.example
            if isinstance(value, tuple):
                inputs[name] = list(value)
            elif (
                isinstance(value, str)
                and isinstance(example, int)
                and not isinstance(example, bool)
                and value.isascii()
                and value.isdigit()
            ):
                inputs[name] = int(value)
            else:
                inputs[name] = value
        return inputs
