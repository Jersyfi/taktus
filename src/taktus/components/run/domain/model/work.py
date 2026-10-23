"""What a step does when it runs, typed per method, read from the bundle's `work` data.

Five kinds are executable in this version. A `rule` step evaluates one of the built-in rules
(`domain.service.rules`) — a constant, a verified artifact, a machine check, the ready standard
of a backlog task, the backlog in its order, the roadmap held against the backlog, spam by
fixed patterns, a contribution's class held to what may be answered, a text template, what a
pattern names in a list of texts, a title in the Conventional Commits form — or
calls a connector operation (`rule: connector`, ADR-0024). A `wait` step waits for a duration
through the clock, or for an external state read through a connector. A `worker`
step hands a task to an execution unit behind the worker contract; an `ml` step does too, a
prediction with its model pinned by digest, and goes to its fallback when the model is unsure
(ADR-0076). An `llm` step asks a model through the model port. Every other method has no
executor yet and is refused before the run starts, so that a run never stops in the middle for a
reason that was known at the beginning.

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
  (`taktusctl run --input`), optionally with `$select` as well;
- `{"$run": "<part>"}` — a part of the run's own record, resolved when the step runs: `id`,
  `process_version`, `failed` — the step that failed and its reason, `{"step", "reason"}`,
  or null while none has (ADR-0097) — and `keys.<step-id>`, the idempotency key that step's
  current attempt carries to a connector, the first attempt's while it has not started, so
  that an earlier step can ask whether what a later one will write is already its own
  (ADR-0099);
- `{"$input": "<name>", "$otherwise": <value>}` — that input where the run was given it, and
  the value otherwise. The value may itself be a `$from` reference: an input the bundle
  declares `required: false` can then stand in for what a step produces, so that whoever
  starts the run by hand may supply it and a trigger need not (ADR-0053).

A `$from` names a step that is a dependency of the step, directly or through others. `$input`
references are resolved when the run is created — the inputs are known then — and may
therefore stand in typed places too: a workspace location, an allowed host.

**When a step runs, and whom it asks first** (ADR-0088, ADR-0097). Beside what it does, a step's
work may carry three keys of its own, read by `control_of` and never part of the typed work:

- `when` — conditions in the shape of a `check` rule's, over earlier results. A step whose
  conditions do not all hold is skipped: it succeeds with the result
  `{"skipped": true, "because": …}`, performs nothing and asks nobody;
- `ask` — the step's act is put to a person as a decision request before it starts, at every
  level, as an anchor would put it: the process declares it, and no tenant configuration
  removes it. `on_decline: continue` makes a declined act a result instead of a halt: the step
  succeeds with `{"declined": true, "by": …, "answer": …}`, and the steps after it read that;
- `on_escalation: true` — the step is no part of the run's sequence. It runs only when the run
  escalates, after the step that failed and before the run ends, and only when every step it
  depends on succeeded; a run that finishes skips it (ADR-0097).

**What a step may see** (ADR-0130). Two more keys set the frame the step runs in:

- `scope: {subject: {"$input": "<name>"}}` — the step serves a case, and the case is about this
  subject. The subject is one of the run's inputs, as its intake gave it, never what a step
  produced: a `$from`, a `$run` or an `$otherwise` in it is refused. Every connector call of
  the step carries the scope;
- `analytic: {source: "<capability>"}` — the step analyses. It reaches no capability but its
  source, through reads only, no host at all, and reads only what analytic steps produced. Its
  source is one the tenant declares free of personal fields. `analytic: true` is a step that
  reads no source of its own.
"""

from __future__ import annotations

import binascii
import hashlib
import json
import math
import re
from base64 import b64decode, b64encode
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from taktus.components.run.domain.model.errors import UnsupportedWork
from taktus.ports.connector import CaseScope
from taktus.ports.worker import CredentialReference, Host, Task, Workspace
from taktus.shared.v1 import Capability, Method, Step, StepId, Value

FROM = "$from"
INPUT = "$input"
SELECT = "$select"
ARTIFACT = "$artifact"
OTHERWISE = "$otherwise"
RUN = "$run"
REFERENCE_KEYS = frozenset({FROM, INPUT, RUN, SELECT, ARTIFACT, OTHERWISE})


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


class ReadyRule(Value):
    """The ready standard of a backlog task (DEC-0051, `domain.service.ready`), over a
    repository's reading of one issue. `issue` is the reading — `number`, `state`,
    `is_pull_request`, `body`, `labels` as names, `milestone` as a title or nothing.

    `expect: ready` is an admission: the issue is open, not a pull request, not claimed, and
    meets the whole standard — three sections, a component, a milestone, one priority label,
    the label `ready`, and nothing open under "Blocked by". What is open is read, not assumed:
    `open_records` are the file names of the directory that holds the open records, and
    `open_issues` the repository's open issues, as numbers or as readings with a `number`.
    `expect: sections_missing` asks the opposite of the content alone: the issue is open, not
    a pull request, and lacks at least one of the three sections. `handed: true` makes the
    admission one of an issue handed to Taktus: it carries the label `to-taktus`, and its "Blocked
    by" names no ADR (DEC-0197).

    The result is `{"number", "ready", "reasons", "missing"}` once the expectation holds; when
    it does not, the step fails naming every reason. The verdict comes from the fields read,
    never from a judgement: admissible for `exact`."""

    rule: Literal["ready"]
    expect: Literal["ready", "sections_missing"]
    issue: Any
    open_records: Any = None
    open_issues: Any = None
    handed: bool = False

    @model_validator(mode="after")
    def _admission_reads_what_is_open(self) -> ReadyRule:
        if self.expect == "ready" and (self.open_records is None or self.open_issues is None):
            raise ValueError("an admission names open_records and open_issues: what blocks is read")
        return self


class BacklogRule(Value):
    """The backlog in its order (DEC-0051, `domain.service.ready.backlog`), over a repository's
    reading of its open issues — the same function `make backlog` runs. `issues` are readings
    as `repository.issues.list` returns them; `open_records` the file names of the directory
    that holds the open records (or entries with a `name`). An issue named under "Blocked by"
    is open while it is among `issues`.

    The result is `{ready, claimed, not_ready, disagreements, text}`: the three groups in the
    order a session takes them, every issue labelled `ready` whose content fails the standard
    (an open blocker is not such a failure: the label stays rightly), and both as text a person
    reads. It never fails on what it finds: finding is its result. Admissible for `exact`."""

    rule: Literal["backlog"]
    issues: Any
    open_records: Any


class RoadmapRule(Value):
    """The roadmap held against the open issues (`domain.service.roadmap`): every item of a
    milestone that names no issue, and every open issue that is work in a milestone whose items
    do not name it. `roadmap` is the roadmap's text; `issues` readings as `issues` above.

    The result is `{milestones, disagreements, text}`. A text in which no milestone is found
    fails the step — it is not a roadmap. Admissible for `exact`."""

    rule: Literal["roadmap"]
    roadmap: Any
    issues: Any


class SpamRule(Value):
    """Whether a text is spam by fixed patterns (UC-1.9, ADR-0088): `text` is a string or a
    list of strings, read as one; `patterns` are regular expressions, searched case-blind.

    The result is `{"spam", "matched"}`: true with the patterns that matched, or false with
    none. It never fails on what it finds: finding is its result. The same text and patterns
    give the same verdict every time: admissible for `exact`. What no pattern names is not
    spam by this rule, and is left to whoever judges next."""

    rule: Literal["spam"]
    text: Any
    patterns: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _patterns_compile(self) -> SpamRule:
        for pattern in self.patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"pattern {pattern!r} does not compile: {error}") from error
        return self


CLASSES = ("defect", "feature", "spam")


class ClassificationRule(Value):
    """A contribution's class, read from a judgement and held to what may be answered
    (UC-1.9, ADR-0088). `answer` is a text of lines `class: …`, `version: …`, `summary: …`, or
    an llm step's whole result, whose `text` is read — and which a skipped step does not have;
    `screened` is a `spam` rule's result; `versions` the versions a contribution may be
    proposed for.

    Screened as spam, the class is `spam` whatever the answer says. Otherwise the answer
    names exactly one of `defect`, `feature`, `spam`; a defect or a feature names one of the
    versions and a summary. Anything else fails the step, so that a judgement beside the
    point never leaves it. The result is `{"class", "version", "summary"}`. The class is the
    judgement's, so the step carries the judgement's exactness class, never `exact`."""

    rule: Literal["classification"]
    answer: Any
    screened: Any
    versions: Any


class TemplateRule(Value):
    """The result is `text` with every `${name}` replaced by the named value; a value that is
    not a string is inserted as its JSON text. A name the values do not carry fails the step."""

    rule: Literal["template"]
    text: str
    values: dict[str, Any] = Field(default_factory=dict)


class ExtractRule(Value):
    """What a pattern names in a list of texts, less what it names in another (ADR-0095).
    `values` and `excluding` are lists — nested lists are read as one — of texts, or of
    entries with a `path` or a `name`, as a changeset's files and a directory listing carry
    them. `pattern` is a regular expression with named groups, searched in each text; `text`
    composes each match from its groups, `${group}`, as a `template` rule composes its text.

    The result is `{"extracted": [...]}`: every distinct text composed from a match among
    `values` that no match among `excluding` composes too, sorted. A list that names nothing is
    an empty result, never a failure; an item that is neither a text nor such an entry fails
    the step. The same lists give the same result every time: admissible for `exact`."""

    rule: Literal["extract"]
    values: Any
    excluding: Any = None
    pattern: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _pattern_names_what_the_text_uses(self) -> ExtractRule:
        try:
            compiled = re.compile(self.pattern)
        except re.error as error:
            raise ValueError(f"pattern {self.pattern!r} does not compile: {error}") from error
        used = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", self.text))
        missing = used - set(compiled.groupindex)
        if missing:
            raise ValueError(f"text names {sorted(missing)}, which the pattern does not group")
        return self


class FilesType(Value):
    """The type a change has whose every file matches `pattern`."""

    pattern: str = Field(min_length=1)
    type: str = Field(min_length=1)

    @model_validator(mode="after")
    def _compiles(self) -> FilesType:
        try:
            re.compile(self.pattern)
        except re.error as error:
            raise ValueError(f"pattern {self.pattern!r} does not compile: {error}") from error
        return self


class CommitTitleRule(Value):
    """A title in the Conventional Commits form, `<type>(<scope>): <summary> (#<number>)`, from
    a sentence such as an issue's title (ADR-0101). The type is one of `types`, taken from the
    first source that gives one: the sentence itself where it is already in the form; a label
    among `labels` that `label_pattern` matches, its group `type`; the changed `files`, where
    every one matches the `pattern` of an entry of `by_files`, that entry's `type`; and last
    `proposal`, a text in which `proposed` is searched, its groups `type` and `scope`.

    A proposal is a variable method's opinion, so the rule holds it to `types` and produces the
    value itself. The scope comes from the sentence or the proposal and is dropped unless it is
    lower-case words. The summary is the sentence, its first letter lower-cased unless its first
    word is an abbreviation, a final full stop dropped.

    The result is `{"title", "type", "scope", "source"}`. No type from any source, two labels
    naming different types, or an empty sentence fails the step. The same inputs give the same
    title every time: admissible for `exact`."""

    rule: Literal["commit_title"]
    title: Any
    number: Any
    types: tuple[str, ...] = Field(min_length=1)
    labels: Any = None
    label_pattern: str | None = None
    files: Any = None
    by_files: tuple[FilesType, ...] = ()
    proposal: Any = None
    proposed: str | None = None

    @model_validator(mode="after")
    def _patterns_group_a_type(self) -> CommitTitleRule:
        for name, pattern in (("label_pattern", self.label_pattern), ("proposed", self.proposed)):
            if pattern is None:
                continue
            try:
                compiled = re.compile(pattern)
            except re.error as error:
                raise ValueError(f"{name} {pattern!r} does not compile: {error}") from error
            if "type" not in compiled.groupindex:
                raise ValueError(f"{name} {pattern!r} has no group `type`")
        for entry in self.by_files:
            if entry.type not in self.types:
                raise ValueError(f"by_files names {entry.type!r}, which is not among the types")
        return self


class Expectation(Value):
    """What a reading must show: the part of the output `select` names, equal to something,
    matching a pattern, or not — the conditions of a `check`, over what was just read.

    `says` is what a reading that does not show it means, for whoever reads the failure: a
    person who must act on it, from the run's output or the comment a process writes. Each
    `${name}` in it is replaced by that field of the reading, as a template inserts a value; a
    name the reading does not carry stays as written. The failure states it before the check
    that did not hold (ADR-0099)."""

    select: str = Field(min_length=1)
    equals: Any | None = None
    matches: str | None = None
    not_matches: str | None = None
    says: str | None = Field(default=None, min_length=1)


class ConnectorRule(Value):
    """The result is what one connector operation answered: its output, the effect it reported
    and what it consumed (`contracts/connector/v1` §5). The operation's capability — every
    segment but the last of its name — chooses the connector; `credentials` name, never hold,
    the requesting identity's credentials for the target. An outward effect the connector
    reports becomes an egress entry in the ledger (ADR-0022).

    A read may carry `expect`: what the reading must show for the step to succeed. A reading
    that does not show it fails the step itself, and is therefore read again when the run is
    resumed — the state outside may have changed since (issue #31). A reading that succeeded is
    a stored result and is never read again; a check in a later step over it would judge the
    old reading for ever."""

    rule: Literal["connector"]
    operation: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*){2,}$")
    # The operation's own input, with references; its shape belongs to the operation.
    input: dict[str, Any] = Field(default_factory=dict)
    credentials: tuple[CredentialReference, ...] = ()
    expect: tuple[Expectation, ...] = ()

    @property
    def capability(self) -> str:
        return self.operation.rsplit(".", 1)[0]


type RuleWork = Annotated[
    ConstantRule
    | VerifyArtifactRule
    | CheckRule
    | ReadyRule
    | BacklogRule
    | RoadmapRule
    | SpamRule
    | ClassificationRule
    | TemplateRule
    | ExtractRule
    | CommitTitleRule
    | ConnectorRule,
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
    capacity_ceiling_seconds: int | None = Field(default=None, ge=1)
    """How long the step may wait for a free place at its worker before it ends with cause
    `capacity` and the run escalates (ADR-0037). None takes the engine's default."""


PREDICT = "ml.predict"
"""The capability an `ml` step requires: a worker that applies a model to rows (ADR-0076)."""

THRESHOLD = re.compile(r"^\s*confidence\s*(<=?)\s*((?:0|1)(?:\.[0-9]+)?|\.[0-9]+)\s*$")
"""The one form of an `ml` step's `fallback.when` the engine evaluates: `confidence < t` or
`confidence <= t`, with `t` from 0 to 1 (ADR-0076 §3)."""

DIGEST = r"^sha256:[0-9a-f]{64}$"


class ModelFile(Value):
    """A model file, pinned by the digest of its bytes: behind a URI the worker fetches, or in
    the step's work. A model is used only as pinned (NTC-0156)."""

    uri: str | None = Field(default=None, pattern=r"^https?://")
    base64: str | None = None
    digest: str = Field(pattern=DIGEST)

    @model_validator(mode="after")
    def _one_place(self) -> ModelFile:
        if (self.uri is None) == (self.base64 is None):
            raise ValueError("a model file is named by a uri or given as base64, one of them")
        if self.base64 is not None:
            try:
                content = b64decode(self.base64, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("the model's base64 is not base64") from error
            if "sha256:" + hashlib.sha256(content).hexdigest() != self.digest:
                raise ValueError("the bytes of the model do not match its digest")
        return self


class Threshold(Value):
    """An `ml` step's fallback condition, read: below `value` — or at it, where `inclusive` —
    the step is unsure and goes to its fallback."""

    value: float = Field(ge=0, le=1)
    inclusive: bool = False

    def unsure(self, confidence: float) -> bool:
        return confidence <= self.value if self.inclusive else confidence < self.value

    def describe(self) -> str:
        return f"confidence {'<=' if self.inclusive else '<'} {self.value:g}"


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
    data_class: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    """The class of the data the prompt carries, as the process declares it: the tenant's
    residency rule for that class steers which model the step is routed to (ADR-0116 §3)."""


LABEL = "label"
"""The label column of the rows a training reads. A feature of that name is renamed."""


def column(name: str) -> str:
    """A feature's column name: never the label's."""
    return f"{name}_" if name == LABEL else name


def row_of(values: Any, features: Any) -> str:
    """One case as the rows an `ml` step predicts: a CSV with a header row and one row, a
    number in every feature column (ADR-0114 §3). `features` are dotted paths into `values`,
    the values a step on a language model rendered its prompt from. A feature that is not
    there, or not a finite number, is a ValueError naming it: the case cannot be predicted."""
    if not isinstance(features, list | tuple) or not features:
        raise ValueError("dataset.features names the numbers to predict from")
    cells: list[str] = []
    for path in features:
        try:
            value = select(values, str(path))
        except (KeyError, IndexError, TypeError):
            raise ValueError(f"the case gives no value for the feature {path!r}") from None
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise ValueError(f"the feature {path!r} is not a finite number: {value!r}")
        cells.append(repr(float(value)))
    header = ",".join(column(str(path)) for path in features)
    return f"{header}\n{','.join(cells)}\n"


class MlWork(WorkerWork):
    """A prediction: the rows of `dataset`, given to a worker that offers `ml.predict`, with the
    step's model file pinned by its digest (ADR-0076). The task the worker receives is built
    from them; a bundle never writes it. `dataset` is `{"csv": <text>}` — the text may be a
    reference to what an earlier step produced — or a source as the worker reads it,
    `{"uri": ...}` or `{"base64": ...}`, with a `digest` where known.

    A step moved from a language model (ADR-0114) names its one case as `{"values": ...,
    "features": [...]}`: the values its prompt was rendered from, and the dotted paths of the
    numbers it predicts from. `fallback` is the language model's work it hands an unsure case
    back to; its step's `fallback.to` names `llm` then. `evaluation` is the model's evaluation
    on held-out cases, which the version carries for its registration (UC-8.4 §2). The worker
    receives neither."""

    model: ModelFile
    dataset: dict[str, Any]
    label: str | None = None
    threshold: Threshold
    fallback: LlmWork | None = None
    evaluation: dict[str, Any] | None = None
    """Read by registration, never by the run."""

    @model_validator(mode="before")
    @classmethod
    def _task_of_a_prediction(cls, given: Any) -> Any:
        if not isinstance(given, Mapping) or "task" in given:
            return given
        inputs: dict[str, Any] = {
            "operation": "predict",
            "model": given.get("model"),
            "dataset": given.get("dataset"),
        }
        if given.get("label") is not None:
            inputs["label"] = given["label"]
        return {
            **given,
            "task": {
                "goal": "apply the step's model to the rows and give each row's class with its "
                "confidence",
                "acceptance": ["every row carries a class and its confidence"],
                "inputs": inputs,
            },
        }

    @model_validator(mode="after")
    def _rows_in_one_place(self) -> MlWork:
        if set(self.dataset) == {"values", "features"}:
            features = self.dataset["features"]
            if not isinstance(features, list | tuple) or not features:
                raise ValueError("dataset.features names the numbers to predict from")
            return self
        if self.fallback is not None:
            raise ValueError(
                "a step that falls back to a language model predicts its one case, given as "
                "dataset {values, features}"
            )
        places = {"csv", "uri", "base64"} & set(self.dataset)
        if len(places) != 1 or not set(self.dataset) <= {"csv", "uri", "base64", "digest"}:
            raise ValueError(
                "dataset is {csv}, {uri} or {base64}, with a digest where known, or "
                "{values, features}"
            )
        return self

    @staticmethod
    def worker_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
        """The task's inputs once references are resolved: rows given as text are handed to the
        worker as the bytes of that text, and one case given as values and features as the
        bytes of its one row. A case without one of its features is a ValueError naming it."""
        dataset = inputs.get("dataset")
        if isinstance(dataset, Mapping) and set(dataset) == {"values", "features"}:
            text = row_of(dataset["values"], dataset["features"])
            rows = {"base64": b64encode(text.encode("utf-8")).decode("ascii")}
            return {**inputs, "dataset": rows}
        if not isinstance(dataset, Mapping) or "csv" not in dataset:
            return dict(inputs)
        text = dataset["csv"]
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        rows = {k: v for k, v in dataset.items() if k != "csv"}
        rows["base64"] = b64encode(text.encode("utf-8")).decode("ascii")
        return {**inputs, "dataset": rows}


def threshold(step: Step) -> Threshold:
    """The fallback condition of an `ml` step, read, or why it cannot be (ADR-0076 §3, §4)."""
    if step.fallback is None:
        raise UnsupportedWork(
            step.id,
            "an ml step names its fallback: a model that is unsure does not guess, it asks "
            "(docs/architecture/methods.md §2)",
        )
    if step.fallback.to not in (Method.HUMAN, Method.LLM):
        raise UnsupportedWork(
            step.id,
            "an ml step falls back to a person, or to the language model it was moved from "
            f"(ADR-0114); not to {step.fallback.to}",
        )
    matched = THRESHOLD.match(step.fallback.when)
    if matched is None or float(matched.group(2)) > 1:
        raise UnsupportedWork(
            step.id,
            f"fallback.when {step.fallback.when!r} is not a threshold the engine evaluates: "
            "write `confidence < t` or `confidence <= t`, t from 0 to 1",
        )
    return Threshold(value=float(matched.group(2)), inclusive=matched.group(1) == "<=")


type Work = RuleWork | WaitWork | WorkerWork | MlWork | LlmWork

WHEN = "when"
ASK = "ask"
ON_ESCALATION = "on_escalation"
EMPTY_WHEN_SKIPPED = "empty_when_skipped"
SCOPE = "scope"
ANALYTIC = "analytic"
CONTROL_KEYS = frozenset({WHEN, ASK, ON_ESCALATION, EMPTY_WHEN_SKIPPED, SCOPE, ANALYTIC})


class Ask(Value):
    """The step's act, put to a person before it starts (ADR-0088). `question`, `situation`
    and `proposal` are templates over `values`, as a `template` rule's text is; `role` is the
    role that decides, `owner` unless named."""

    question: str = Field(min_length=1)
    situation: str | None = None
    proposal: str | None = None
    """What option A performs, in a reader's words."""
    values: dict[str, Any] = Field(default_factory=dict)
    role: str = Field(default="owner", min_length=1)
    on_decline: Literal["halt", "continue"] = "halt"


class Analytic(Value):
    """The step analyses (ADR-0130). `source` is the one capability it reads, which the tenant
    declares free of personal fields; None for a step that reads no source of its own."""

    source: Capability | None = None

    @model_validator(mode="before")
    @classmethod
    def _true_reads_no_source(cls, given: Any) -> Any:
        return {} if given is True else given


class Control(Value):
    """When a step runs, whom it asks first and what it may see: the keys of a step's work that
    are not what the step does (ADR-0088, ADR-0097, ADR-0130)."""

    when: tuple[Condition, ...] = ()
    ask: Ask | None = None
    on_escalation: bool = False
    """The step runs only when the run escalates, and asks nobody: the run has gone to a person
    already (ADR-0097)."""
    empty_when_skipped: bool = False
    """A run that finished with this step skipped, because its `when` did not hold, found
    nothing to do: it ends `empty`, not `ok` (ADR-0107 §2)."""
    scope: CaseScope | None = None
    """The case the step serves, with its subject resolved from the run's inputs (ADR-0130)."""
    analytic: Analytic | None = None
    """The step analyses, and its frame holds nothing outward (ADR-0130)."""

    @model_validator(mode="after")
    def _a_step_on_escalation_asks_nobody(self) -> Control:
        if self.scope is not None and self.analytic is not None:
            raise ValueError("a step serves a case or analyses, never both")
        if self.on_escalation and self.ask is not None:
            raise ValueError("a step that runs on escalation asks nobody")
        if self.empty_when_skipped and not self.when:
            raise ValueError(
                "a step marks its run empty when its `when` does not hold; it has none"
            )
        if self.empty_when_skipped and self.on_escalation:
            raise ValueError("a step that runs on escalation never marks a finished run empty")
        return self

    def referenced(self) -> list[Any]:
        """The untyped parts that may carry `$from` references."""
        found: list[Any] = [condition.value for condition in self.when]
        if self.ask is not None:
            found.append(self.ask.values)
        return found


def control_of(
    step: Step, work: Mapping[str, Any] | None, inputs: Mapping[str, Any] | None = None
) -> Control:
    """The step's `when`, `ask` and frame, with `$input` references resolved, or
    UnsupportedWork."""
    given = {key: work[key] for key in CONTROL_KEYS if key in work} if work else {}
    if not given:
        return Control()
    if SCOPE in given and (why := not_from_intake(given[SCOPE])) is not None:
        raise UnsupportedWork(step.id, f"work.scope: {why}")
    try:
        return Control.model_validate(resolve_inputs(given, inputs or {}))
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise UnsupportedWork(step.id, f"work.{where}: {first['msg']}") from error
    except KeyError as error:
        raise UnsupportedWork(step.id, f"work: the run has no input {error.args[0]!r}") from error


def not_from_intake(scope: Any) -> str | None:
    """Why a step's `scope` does not name its subject from the run's inputs, or None. The
    subject is exactly one `$input` reference, with a `$select` at most: a `$from`, a `$run` or
    an `$otherwise` would let a step's output, or a default, choose whose data is seen
    (ADR-0130)."""
    if not isinstance(scope, Mapping) or set(scope) != {"subject"}:
        return "a scope names its subject, and nothing else: {subject: {$input: <name>}}"
    subject = scope["subject"]
    if (
        not isinstance(subject, Mapping)
        or INPUT not in subject
        or not set(subject)
        <= {
            INPUT,
            SELECT,
        }
    ):
        return (
            "the subject is one of the run's inputs, as its intake gave it — {$input: <name>} "
            "— never a step's result, the run's record or a default"
        )
    return None


_RULE: TypeAdapter[RuleWork] = TypeAdapter(RuleWork)


def parse_work(
    step: Step, work: Mapping[str, Any] | None, inputs: Mapping[str, Any] | None = None
) -> Work:
    """The typed work of a step, with `$input` references resolved, or UnsupportedWork naming
    what is wrong."""
    try:
        given = (
            None
            if work is None
            else resolve_inputs(
                {key: value for key, value in work.items() if key not in CONTROL_KEYS},
                inputs or {},
            )
        )
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
        if step.method is Method.ML:
            if given is None:
                raise UnsupportedWork(
                    step.id, "an ml step names its rows and its model under `work`"
                )
            if PREDICT not in (step.required_capabilities or ()):
                raise UnsupportedWork(step.id, f"an ml step requires {PREDICT}")
            read = MlWork.model_validate({**given, "threshold": threshold(step).model_dump()})
            to = None if step.fallback is None else step.fallback.to
            if to is Method.LLM and read.fallback is None:
                raise UnsupportedWork(
                    step.id,
                    "the step falls back to llm, and its work names no language model's work "
                    "under `fallback` to hand an unsure case to",
                )
            if to is not Method.LLM and read.fallback is not None:
                raise UnsupportedWork(
                    step.id,
                    "the work names a language model's work under `fallback`, and the step "
                    f"falls back to {to}",
                )
            return read
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


def escalation_steps(work: Mapping[StepId, Mapping[str, Any]]) -> frozenset[StepId]:
    """The steps whose work says `on_escalation: true` (ADR-0097)."""
    return frozenset(
        step_id for step_id, given in work.items() if given and given.get(ON_ESCALATION) is True
    )


def empty_markers(work: Mapping[StepId, Mapping[str, Any]]) -> frozenset[StepId]:
    """The steps whose work says `empty_when_skipped: true` (ADR-0107 §2)."""
    return frozenset(
        step_id
        for step_id, given in work.items()
        if given and given.get(EMPTY_WHEN_SKIPPED) is True
    )


def is_reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and set(value.keys()) <= REFERENCE_KEYS
        and sum(key in value for key in (FROM, INPUT, RUN)) == 1
        and (OTHERWISE not in value or INPUT in value)
    )


def references(value: Any) -> set[StepId]:
    """Every step a value refers to through `$from`, at any depth, also in what an `$input`
    stands in for when the run was not given it."""
    found: set[StepId] = set()
    if isinstance(value, Mapping):
        if is_reference(value):
            if FROM in value and isinstance(value[FROM], str):
                found.add(value[FROM])
            if OTHERWISE in value:
                found |= references(value[OTHERWISE])
        else:
            for item in value.values():
                found |= references(item)
    elif isinstance(value, list | tuple):
        for item in value:
            found |= references(item)
    return found


def resolve_inputs(value: Any, inputs: Mapping[str, Any]) -> Any:
    """The value with every `$input` reference replaced by the run's input, or by its
    `$otherwise` where the run was not given it; `$from` references stay for the run to resolve.
    An input the run does not have and no `$otherwise` stands in for is a KeyError."""
    if isinstance(value, Mapping):
        if is_reference(value) and INPUT in value:
            name = str(value[INPUT])
            if name not in inputs and OTHERWISE in value:
                return resolve_inputs(value[OTHERWISE], inputs)
            return select(inputs[name], value.get(SELECT))
        return {key: resolve_inputs(item, inputs) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [resolve_inputs(item, inputs) for item in value]
    return value


def resolve(
    value: Any,
    results: Mapping[StepId, Any],
    artifacts: Mapping[str, Any],
    record: Mapping[str, Any] | None = None,
) -> Any:
    """The value with every `$from` reference replaced by the referenced result, selected
    where asked; `artifacts` maps `<step-id>/<artifact-id>` to loaded content. A `$run`
    reference is replaced by the part of `record`, the run's own (ADR-0097), that it names; one
    without a record is a KeyError."""
    if isinstance(value, Mapping):
        if is_reference(value) and FROM in value:
            step_id = str(value[FROM])
            if ARTIFACT in value:
                return select(artifacts[f"{step_id}/{value[ARTIFACT]}"], value.get(SELECT))
            return select(results[step_id], value.get(SELECT))
        if is_reference(value) and RUN in value:
            if record is None:
                raise KeyError(RUN)
            return select(select(record, value[RUN]), value.get(SELECT))
        return {key: resolve(item, results, artifacts, record) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [resolve(item, results, artifacts, record) for item in value]
    return value


def artifact_references(value: Any) -> set[tuple[StepId, str]]:
    """Every (step, artifact) a value refers to through `$from` with `$artifact`."""
    found: set[tuple[StepId, str]] = set()
    if isinstance(value, Mapping):
        if is_reference(value):
            if FROM in value and ARTIFACT in value:
                found.add((str(value[FROM]), str(value[ARTIFACT])))
            if OTHERWISE in value:
                found |= artifact_references(value[OTHERWISE])
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
    if isinstance(work, MlWork) and work.fallback is not None:
        return [work.task.inputs, work.fallback.values]
    if isinstance(work, WorkerWork):
        return [work.task.inputs]
    if isinstance(work, ConnectorRule):
        return [work.input]
    if isinstance(work, CheckRule):
        return [condition.value for condition in work.conditions]
    if isinstance(work, ReadyRule):
        return [work.issue, work.open_records, work.open_issues]
    if isinstance(work, BacklogRule):
        return [work.issues, work.open_records]
    if isinstance(work, RoadmapRule):
        return [work.roadmap, work.issues]
    if isinstance(work, SpamRule):
        return [work.text]
    if isinstance(work, ClassificationRule):
        return [work.answer, work.screened, work.versions]
    if isinstance(work, TemplateRule | LlmWork):
        return [work.values]
    if isinstance(work, ExtractRule):
        return [work.values, work.excluding]
    if isinstance(work, CommitTitleRule):
        return [work.title, work.number, work.labels, work.files, work.proposal]
    if isinstance(work, WaitWork) and work.until is not None:
        return [work.until.input]
    return []
