"""Process, process version, edge, trigger and service level (control-plane.md §4)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import Field, model_validator

from taktus.components.process.domain.model.errors import InvalidProcess
from taktus.components.process.domain.model.evaluation import EvaluationSpec
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
    required: bool = True
    """False: a run may start without it, and a trigger need not give it. Every reference to
    it then names what stands in for it, under `$otherwise` (ADR-0053)."""


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


class Expect(Value):
    """When a run of the process is expected (ADR-0107): at every slot of a `schedule`, or
    within a `gap` of the last run's start; and that a run ends within its `bound`. A run
    that does not happen as expected, or does not end within its bound, raises an incident."""

    schedule: str | None = Field(default=None, min_length=1)
    gap: timedelta | None = None
    """The longest time between the starts of two runs."""
    bound: timedelta | None = None
    """The longest time a run may take from its start to its end."""

    @model_validator(mode="after")
    def _says_something(self) -> Expect:
        if self.schedule is None and self.gap is None and self.bound is None:
            raise ValueError("`expect` names a `schedule`, a `gap` or a `bound`")
        if self.schedule is not None and self.gap is not None:
            raise ValueError("`expect` names a `schedule` or a `gap`, not both")
        if self.schedule is not None:
            schedule.parse(self.schedule)  # an InvalidSchedule is a ValueError and says why
        for name, value in (("gap", self.gap), ("bound", self.bound)):
            if value is not None and value <= timedelta(0):
                raise ValueError(f"`expect.{name}` is a time longer than nothing")
        return self


OPEN_WORK_KIND = r"^[a-z][a-z0-9_]*$"
"""A kind of open outcome is a token: `pull_requests`, `tasks`, `drafts`."""
CHECK_EVERY = timedelta(minutes=15)
"""How often a run waiting at a cap counts again, where the cap names no interval (NTC-0226)."""


class OpenWorkCount(Value):
    """How the outcomes of one kind that are open outside are read: one read operation of a
    connector, with a literal input, and where in its output they are — a list, counted by its
    length, or a number (ADR-0132 §2)."""

    operation: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$")
    input: Mapping[str, Any] = Field(default_factory=dict)
    credentials: tuple[Mapping[str, Any], ...] = ()
    """The credentials the read names, by name only, as a connector step names them."""
    select: str | None = Field(default=None, min_length=1)
    """A dotted path into the output; None counts the output itself."""


class OpenWorkCap(Value):
    """How many outcomes of one kind may wait at once (ADR-0132 §1). While as many are open, a
    run of the process starts nothing and waits."""

    cap: int = Field(ge=1)
    reading: OpenWorkCount | None = None
    """How the open outcomes are read outside; None counts only the process's runs in flight."""
    check_every: timedelta = CHECK_EVERY
    """How often a waiting run counts again."""

    @model_validator(mode="after")
    def _checks_now_and_then(self) -> OpenWorkCap:
        if self.check_every < timedelta(seconds=1):
            raise ValueError("`check_every` is at least a second")
        return self


DEADLINE_NAME = r"^[a-z][a-z0-9_]*$"
"""A deadline's name is a token: `first_answer`, `renewal`."""
ROLE = r"^[a-z][a-z0-9_.-]*$"
"""A role, as the organisation's structure names it."""


class DeadlineAction(Value):
    """What a deadline does at its lead time or its limit: exactly one of a reminder to a role,
    an escalation to a role, or a start of a process (ADR-0133 §1). Never a person."""

    kind: Literal["remind", "escalate", "start"]
    role: str | None = Field(default=None, pattern=ROLE)
    process: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]*$")
    inputs: Mapping[str, Any] = Field(default_factory=dict)
    """The literal inputs a started run is given."""

    @model_validator(mode="after")
    def _one_target(self) -> DeadlineAction:
        if self.kind == "start":
            if self.process is None or self.role is not None:
                raise ValueError("a start names a process and no role")
        elif self.role is None or self.process is not None or self.inputs:
            raise ValueError(f"a {self.kind} names a role, and nothing else")
        return self


class DeadlineDeclaration(Value):
    """One deadline of the process (ADR-0133 §1): the moment it starts from, its limit, an
    optional lead time, how it counts, the step whose finish meets it, and its actions."""

    start: Literal["run", "after", "date"]
    after: StepId | None = None
    """The step whose finish starts it, for `after`."""
    date_input: str | None = Field(default=None, min_length=1)
    """The input that names its moment, for `date`."""
    limit: timedelta
    lead: timedelta | None = None
    working: bool = False
    """True: the limit and the lead count in the tenant's working time."""
    until: StepId
    at_lead: DeadlineAction | None = None
    at_limit: DeadlineAction

    @model_validator(mode="after")
    def _sound(self) -> DeadlineDeclaration:
        if (self.start == "after") != (self.after is not None):
            raise ValueError("`from: {after: <step>}` names the step it starts after")
        if (self.start == "date") != (self.date_input is not None):
            raise ValueError("`from: {date: <input>}` names the input that holds the date")
        if self.limit < timedelta(0):
            raise ValueError("`limit` is no shorter than nothing")
        if self.lead is not None and self.lead <= timedelta(0):
            raise ValueError("`lead` is longer than nothing")
        if self.lead is not None and self.at_lead is None:
            raise ValueError("a `lead` without `at_lead` does nothing; name its action")
        if self.at_lead is not None and self.lead is None:
            raise ValueError("`at_lead` names an action and no `lead` says when")
        return self


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
    expect: Expect | None = None
    """When a run is expected (ADR-0107). None: every schedule trigger expects a run at
    each of its slots, and nothing else is expected."""
    work: Mapping[StepId, Work] = Field(default_factory=dict)
    limits: Work | None = None
    inputs: Mapping[str, InputDeclaration] = Field(default_factory=dict)
    """What a run of this version is given when it starts, by name: what `$input` references
    in the work resolve to. A run that lacks a required one is refused before anything runs."""
    open_work: Mapping[str, OpenWorkCap] = Field(default_factory=dict)
    """The cap on each kind of the process's open outcomes, by kind (ADR-0132). Only a person
    changes it: a version that changes it is registered only with a person's approval."""
    deadlines: Mapping[str, DeadlineDeclaration] = Field(default_factory=dict)
    """The deadlines of each run, by name (ADR-0133). Taktus keeps them; no worker and no
    outside timer does."""
    evaluation: EvaluationSpec | None = None
    """The process's evaluation cases, its scorers and the schedule they run on without a
    change (ADR-0134 §1). None: a change is held to no cases, and nothing measures drift."""
    author: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _valid_graph(self) -> ProcessVersion:
        findings = validate_graph(self.steps)
        findings.extend(self._evaluation_findings())
        findings.extend(
            f"`open_work` names the kind {kind!r}; a kind is a lowercase token such as "
            "pull_requests"
            for kind in self.open_work
            if re.fullmatch(OPEN_WORK_KIND, kind) is None
        )
        ids = {step.id for step in self.steps}
        for name, deadline in self.deadlines.items():
            if re.fullmatch(DEADLINE_NAME, name) is None:
                findings.append(
                    f"`deadlines` names {name!r}; a deadline's name is a lowercase token"
                )
            if deadline.after is not None and deadline.after not in ids:
                findings.append(
                    f"the deadline {name!r} starts after {deadline.after!r}, which is not a "
                    "step of this process"
                )
            if deadline.until not in ids:
                findings.append(
                    f"the deadline {name!r} is met by {deadline.until!r}, which is not a step "
                    "of this process"
                )
            if deadline.date_input is not None and deadline.date_input not in self.inputs:
                findings.append(
                    f"the deadline {name!r} starts at the input {deadline.date_input!r}, which "
                    "the process does not declare under `inputs`"
                )
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
            missing = sorted(set(self.required_inputs) - trigger.given)
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

    def _evaluation_findings(self) -> list[str]:
        """Why the declared evaluation cannot hold against this version (ADR-0134 §1)."""
        if self.evaluation is None:
            return []
        producing = {step.id for step in self.steps if step.exactness is not None}
        found = [
            f"`evaluation`: a scorer scores the step {scorer.step!r}, which is not a step of "
            "this process that produces a result"
            for scorer in self.evaluation.scorers
            if scorer.step not in producing
        ]
        scored = self.evaluation.scored_steps
        required = {name for name, given in self.inputs.items() if given.required}
        for case in self.evaluation.cases:
            where = f"`evaluation`: the case {case.id!r}"
            found.extend(
                f"{where} names a target for {step_id!r}, which no scorer scores"
                for step_id in case.targets
                if step_id not in scored
            )
            unknown = sorted(set(case.inputs) - set(self.inputs))
            if unknown:
                found.append(
                    f"{where} gives {', '.join(unknown)}, which the process does not declare "
                    "under `inputs`"
                )
            missing = sorted(required - set(case.inputs))
            if missing:
                found.append(f"{where} gives no value for the input(s) {', '.join(missing)}")
        return found

    @property
    def expected_schedules(self) -> tuple[str, ...]:
        """The schedules a run is expected at every slot of: the declared one, or without a
        declared schedule or gap, every schedule trigger's (ADR-0107 §1)."""
        if self.expect is not None and self.expect.schedule is not None:
            return (self.expect.schedule,)
        if self.expect is not None and self.expect.gap is not None:
            return ()
        return tuple(dict.fromkeys(t.schedule for t in self.triggers if t.schedule is not None))

    @property
    def required_inputs(self) -> tuple[str, ...]:
        """The inputs a run of this version cannot start without."""
        return tuple(name for name, given in self.inputs.items() if given.required)

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
