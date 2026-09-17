"""What a step does when it runs, typed per method, read from the bundle's `work` data.

Three kinds are executable in this version. A `rule` step evaluates one of the built-in rules
(`domain.service.rules`). A `wait` step waits for a duration through the clock. A `worker` step
hands a task to an execution unit behind the worker contract. Every other method has no
executor yet and is refused before the run starts, so that a run never stops in the middle for
a reason that was known at the beginning.

Inside a worker task's `inputs`, the object `{"$from": "<step-id>"}` is replaced at run time by
the result of that step — the value a rule produced, or the artifacts a worker produced. The
named step must be a dependency of the step, directly or through others.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from taktus.components.run.domain.model.errors import UnsupportedWork
from taktus.ports.worker import Host, Task, Workspace
from taktus.shared.v1 import Method, Step, StepId, Value

FROM = "$from"


class ConstantRule(Value):
    """The result is the given value. Trivially exact: there is nothing to get wrong."""

    rule: Literal["constant"]
    # The value is whatever JSON the bundle carries; the rule does not interpret it.
    value: Any


class VerifyArtifactRule(Value):
    """The result is the text of one artifact an earlier step produced, after two machine
    checks: its bytes hash to the digest the producer announced, and — when a pattern is
    given — its text matches the pattern. This is ADR-0014 §4.1 in code: a worker may propose;
    the value that leaves the step comes from the check."""

    rule: Literal["verify_artifact"]
    step: StepId
    artifact: str = Field(min_length=1)
    pattern: str | None = None


type RuleWork = Annotated[ConstantRule | VerifyArtifactRule, Field(discriminator="rule")]


class WaitWork(Value):
    seconds: float = Field(default=0, ge=0)


class WorkerWork(Value):
    task: Task
    max_steps: int = Field(default=100, ge=1)
    allowed_hosts: tuple[Host, ...] = ()
    """The hosts the worker may reach for this step; nothing else. Empty — the default — means
    no outbound access, which is right for most work."""
    workspace: Workspace = Workspace(kind="none")


type Work = RuleWork | WaitWork | WorkerWork

_RULE: TypeAdapter[RuleWork] = TypeAdapter(RuleWork)


def parse_work(step: Step, work: Mapping[str, Any] | None) -> Work:
    """The typed work of a step, or UnsupportedWork naming what is wrong."""
    try:
        if step.method is Method.RULE:
            if work is None:
                raise UnsupportedWork(step.id, "a rule step names its rule under `work`")
            return _RULE.validate_python(dict(work))
        if step.method is Method.WAIT:
            return WaitWork.model_validate(dict(work or {}))
        if step.method is Method.WORKER:
            if work is None:
                raise UnsupportedWork(step.id, "a worker step carries its task under `work`")
            if not step.required_capabilities:
                raise UnsupportedWork(step.id, "a worker step names the capabilities it requires")
            return WorkerWork.model_validate(dict(work))
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise UnsupportedWork(
            step.id, f"work{'.' + where if where else ''}: {first['msg']}"
        ) from error
    raise UnsupportedWork(step.id, f"no executor for method {step.method} in this version")


def references(value: Any) -> set[StepId]:
    """Every step a value refers to through `$from`, at any depth."""
    found: set[StepId] = set()
    if isinstance(value, Mapping):
        if set(value.keys()) == {FROM} and isinstance(value[FROM], str):
            found.add(value[FROM])
        else:
            for item in value.values():
                found |= references(item)
    elif isinstance(value, list | tuple):
        for item in value:
            found |= references(item)
    return found


def resolve(value: Any, results: Mapping[StepId, Any]) -> Any:
    """The value with every `$from` replaced by the referenced result."""
    if isinstance(value, Mapping):
        if set(value.keys()) == {FROM} and isinstance(value[FROM], str):
            return results[value[FROM]]
        return {key: resolve(item, results) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [resolve(item, results) for item in value]
    return value
