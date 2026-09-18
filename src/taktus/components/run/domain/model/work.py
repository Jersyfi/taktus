"""What a step does when it runs, typed per method, read from the bundle's `work` data.

Four kinds are executable in this version. A `rule` step evaluates one of the built-in rules
(`domain.service.rules`) — a constant, a verified artifact, a machine check, a text template —
or calls a connector operation (`rule: connector`, ADR-0024). A `wait` step waits for a
duration through the clock, or for an external state read through a connector. A `worker`
step hands a task to an execution unit behind the worker contract. An `llm` step asks a model
through the model port. Every other method has no executor yet and is refused before the run
starts, so that a run never stops in the middle for a reason that was known at the beginning.

**References.** Inside the untyped parts of a step's work — a worker task's `inputs`, a
connector call's `input`, the values of a template, a check or a prompt — an object with a
`$from` or `$input` key is replaced at run time:

- `{"$from": "<step-id>"}` — the result of that step: the value a rule produced, the text an
  llm step produced, or `{"artifacts": [...]}` for a worker step;
- `{"$from": "<step-id>", "$select": "a.b.0"}` — one part of it, by a dotted path over keys
  and list positions;
- `{"$from": "<step-id>", "$artifact": "<artifact-id>"}` — the content of that artifact of
  that step: parsed when its media type is JSON, text otherwise; `$select` applies to it;
- `{"$input": "<name>"}` — one of the run's inputs, given when the run starts
  (`taktusctl run --input`), optionally with `$select` as well.

A `$from` names a step that is a dependency of the step, directly or through others. `$input`
references are resolved when the run is created — the inputs are known then — and may
therefore stand in typed places too: a workspace location, an allowed host.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from taktus.components.run.domain.model.errors import UnsupportedWork
from taktus.ports.worker import CredentialReference, Host, Task, Workspace
from taktus.shared.v1 import Method, Step, StepId, Value

FROM = "$from"
INPUT = "$input"
SELECT = "$select"
ARTIFACT = "$artifact"
REFERENCE_KEYS = frozenset({FROM, INPUT, SELECT, ARTIFACT})


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


class Condition(Value):
    """One machine check over a value: equal to something, matching a pattern, or not. A value
    that is not a string is matched as its JSON text. `equals: null` counts as not given."""

    # The value under test, usually a reference.
    value: Any
    equals: Any | None = None
    matches: str | None = None
    not_matches: str | None = None


class CheckRule(Value):
    """The result is the checked values, once every condition holds. A condition that does not
    hold fails the step: nothing leaves it, and the run goes to a person. The verdict comes
    from the values checked — a pipeline's state, an issue's fields — never from a judgement,
    which is what makes this rule admissible for `exact`."""

    rule: Literal["check"]
    conditions: tuple[Condition, ...] = Field(min_length=1)


class TemplateRule(Value):
    """The result is `text` with every `${name}` replaced by the named value; a value that is
    not a string is inserted as its JSON text. A name the values do not carry fails the step."""

    rule: Literal["template"]
    text: str
    values: dict[str, Any] = Field(default_factory=dict)


class ConnectorRule(Value):
    """The result is what one connector operation answered: its output, the effect it reported
    and what it consumed (`contracts/connector/v1` §5). The operation's capability — every
    segment but the last of its name — chooses the connector; `credentials` name, never hold,
    the requesting identity's credentials for the target. An outward effect the connector
    reports becomes an egress entry in the ledger (ADR-0022)."""

    rule: Literal["connector"]
    operation: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$")
    # The operation's own input, with references; its shape belongs to the operation.
    input: dict[str, Any] = Field(default_factory=dict)
    credentials: tuple[CredentialReference, ...] = ()

    @property
    def capability(self) -> str:
        return self.operation.rsplit(".", 1)[0]


type RuleWork = Annotated[
    ConstantRule | VerifyArtifactRule | CheckRule | TemplateRule | ConnectorRule,
    Field(discriminator="rule"),
]


class WaitUntil(Value):
    """An external state, read through a connector operation until the selected part of its
    output is one of the expected values. Polling is bounded: past `timeout_seconds` the wait
    fails and the run goes to a person."""

    operation: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$")
    input: dict[str, Any] = Field(default_factory=dict)
    credentials: tuple[CredentialReference, ...] = ()
    select: str = Field(min_length=1)
    expect: tuple[Any, ...] = Field(min_length=1)
    poll_seconds: float = Field(default=30, gt=0)
    timeout_seconds: float = Field(default=1800, gt=0)

    @property
    def capability(self) -> str:
        return self.operation.rsplit(".", 1)[0]


class WaitWork(Value):
    seconds: float = Field(default=0, ge=0)
    until: WaitUntil | None = None


class WorkerWork(Value):
    task: Task
    max_steps: int = Field(default=100, ge=1)
    allowed_hosts: tuple[Host, ...] = ()
    """The hosts the worker may reach for this step; nothing else. Empty — the default — means
    no outbound access, which is right for most work."""
    workspace: Workspace = Workspace(kind="none")
    credentials: tuple[CredentialReference, ...] = ()
    """The credentials the assignment references by name; the execution adapter, or whoever
    runs an endpoint worker, supplies the values."""


class LlmWork(Value):
    """A prompt to a model of the named purpose; the result is the text the model answered,
    once it passes the check. The check is what makes the step `sourced` rather than `free`:
    a pattern the answer must match, so that a model that answered beside the point fails the
    step instead of passing its answer on."""

    purpose: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    system: str | None = None
    prompt: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    max_output_tokens: int = Field(default=2048, ge=1)
    pattern: str | None = None


type Work = RuleWork | WaitWork | WorkerWork | LlmWork

_RULE: TypeAdapter[RuleWork] = TypeAdapter(RuleWork)


def parse_work(
    step: Step, work: Mapping[str, Any] | None, inputs: Mapping[str, Any] | None = None
) -> Work:
    """The typed work of a step, with `$input` references resolved, or UnsupportedWork naming
    what is wrong."""
    try:
        given = None if work is None else resolve_inputs(dict(work), inputs or {})
        if step.method is Method.RULE:
            if given is None:
                raise UnsupportedWork(step.id, "a rule step names its rule under `work`")
            return _RULE.validate_python(given)
        if step.method is Method.WAIT:
            return WaitWork.model_validate(given or {})
        if step.method is Method.WORKER:
            if given is None:
                raise UnsupportedWork(step.id, "a worker step carries its task under `work`")
            if not step.required_capabilities:
                raise UnsupportedWork(step.id, "a worker step names the capabilities it requires")
            return WorkerWork.model_validate(given)
        if step.method is Method.LLM:
            if given is None:
                raise UnsupportedWork(step.id, "an llm step carries its prompt under `work`")
            return LlmWork.model_validate(given)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise UnsupportedWork(
            step.id, f"work{'.' + where if where else ''}: {first['msg']}"
        ) from error
    except KeyError as error:
        raise UnsupportedWork(step.id, f"work: the run has no input {error.args[0]!r}") from error
    raise UnsupportedWork(step.id, f"no executor for method {step.method} in this version")


def is_reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and set(value.keys()) <= REFERENCE_KEYS
        and (FROM in value) != (INPUT in value)
    )


def references(value: Any) -> set[StepId]:
    """Every step a value refers to through `$from`, at any depth."""
    found: set[StepId] = set()
    if isinstance(value, Mapping):
        if is_reference(value):
            if FROM in value and isinstance(value[FROM], str):
                found.add(value[FROM])
        else:
            for item in value.values():
                found |= references(item)
    elif isinstance(value, list | tuple):
        for item in value:
            found |= references(item)
    return found


def resolve_inputs(value: Any, inputs: Mapping[str, Any]) -> Any:
    """The value with every `$input` reference replaced by the run's input; `$from` references
    stay for the run to resolve. An input the run does not have is a KeyError."""
    if isinstance(value, Mapping):
        if is_reference(value) and INPUT in value:
            return select(inputs[str(value[INPUT])], value.get(SELECT))
        return {key: resolve_inputs(item, inputs) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [resolve_inputs(item, inputs) for item in value]
    return value


def resolve(value: Any, results: Mapping[StepId, Any], artifacts: Mapping[str, Any]) -> Any:
    """The value with every `$from` reference replaced by the referenced result, selected
    where asked; `artifacts` maps `<step-id>/<artifact-id>` to loaded content."""
    if isinstance(value, Mapping):
        if is_reference(value) and FROM in value:
            step_id = str(value[FROM])
            if ARTIFACT in value:
                return select(artifacts[f"{step_id}/{value[ARTIFACT]}"], value.get(SELECT))
            return select(results[step_id], value.get(SELECT))
        return {key: resolve(item, results, artifacts) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [resolve(item, results, artifacts) for item in value]
    return value


def artifact_references(value: Any) -> set[tuple[StepId, str]]:
    """Every (step, artifact) a value refers to through `$from` with `$artifact`."""
    found: set[tuple[StepId, str]] = set()
    if isinstance(value, Mapping):
        if is_reference(value):
            if FROM in value and ARTIFACT in value:
                found.add((str(value[FROM]), str(value[ARTIFACT])))
        else:
            for item in value.values():
                found |= artifact_references(item)
    elif isinstance(value, list | tuple):
        for item in value:
            found |= artifact_references(item)
    return found


def select(value: Any, path: Any) -> Any:
    """One part of a value by a dotted path — keys of objects, positions of lists — or the
    value itself without a path. A part that is not there is a KeyError naming the path."""
    if path is None:
        return value
    current = value
    for part in str(path).split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list | tuple) and part.lstrip("-").isdigit():
            try:
                current = current[int(part)]
            except IndexError:
                raise KeyError(path) from None
        else:
            raise KeyError(path)
    return current


def referenced_values(work: Work) -> list[Any]:
    """The untyped parts of a work that may carry `$from` references."""
    if isinstance(work, WorkerWork):
        return [work.task.inputs]
    if isinstance(work, ConnectorRule):
        return [work.input]
    if isinstance(work, CheckRule):
        return [condition.value for condition in work.conditions]
    if isinstance(work, TemplateRule | LlmWork):
        return [work.values]
    if isinstance(work, WaitWork) and work.until is not None:
        return [work.until.input]
    return []
