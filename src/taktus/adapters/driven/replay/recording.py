"""The recording of a run: what a replay answers its steps with (ADR-0108).

A recording is a directory. `recording.json` holds the run as far as a replay needs it: the
process and its version, the inputs, the budget and margin it was held to, where it ended, and
per step the state it reached and, for a step that left the engine, its answer. The answer of a
connector call or a model call is the result document the engine kept, in a file of its own
under `results/`; the artifacts of a worker step are files under `artifacts/<step>/`. They are
data, never code, and a replay reads nothing else.

**Content-free where the ledger is.** What the ledger carries as a digest, a recording carries
as a digest: what a step sent is recorded as the digest of the request and a digest per part
of it, never the request itself. What a step received is the content the steps after it read,
and is kept, as the object store keeps it. No identity of a person, no reason in words and no
secret value is recorded; the export refuses a recording in which it finds a known secret.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import Field

from taktus.ports.connector import Operation
from taktus.shared.v1 import Digest, Value

FORMAT: Final = "taktus.recording/v1"
RECORDING = "recording.json"
RESULTS = "results"
ARTIFACTS = "artifacts"

type Kind = Literal["connector", "wait", "model", "worker"]
"""What the step asked outside the engine: a connector call, a wait on a connector's state, a
model's completion, a worker's assignment."""

type Taken = Literal["local", "instance"]
"""Where the recorded run ran: against the repository's fakes on a developer's machine, or on
an instance."""


class Request(Value):
    """What the step sent, content-free: the digest of the request, and of each of its parts —
    a top-level field, or a field of a top-level object — so that a replay that sends another
    request can name what differs without anyone having kept what was sent."""

    digest: Digest
    parts: dict[str, Digest] = Field(default_factory=dict)


class RecordedArtifact(Value):
    """One artifact a worker step produced, and the file that holds its bytes."""

    id: str = Field(min_length=1)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    media_type: str | None = None
    file: str = Field(min_length=1)


class Observed(Value):
    """What ended a wait in the recorded run. A wait keeps no result (ADR-0018), so the value
    it saw is not known; it was one of those it expected, and the replay answers with the
    first of them."""

    select: str = Field(min_length=1)
    value: Any


class Answer(Value):
    """How the outside answered one step of the recorded run."""

    kind: Kind
    adapter: str = Field(min_length=1)
    """The adapter identifier that served the step, as the ledger names it."""
    version: str | None = None
    """The version the adapter declared; for a model, the model that answered."""
    operation: str | None = None
    """For a connector call and a wait: the operation."""
    purpose: str | None = None
    """For a model call: the purpose the step names."""
    capabilities: tuple[str, ...] = ()
    """For a worker step: the capabilities it requires."""
    request: Request
    outcome: Literal["succeeded", "failed", "stopped"]
    estimate: dict[str, Any] | None = None
    """What the step was estimated to use, as the adapter said (a quantities document)."""
    consumption: dict[str, Any] | None = None
    """What the step used (a consumption document)."""
    result: str | None = None
    """For a connector call and a model call that succeeded: the file under `results/` that
    holds the result document."""
    observed: Observed | None = None
    artifacts: tuple[RecordedArtifact, ...] = ()


class Step(Value):
    """One step of the recorded run."""

    id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    state: str = Field(min_length=1)
    """The state the step reached: `succeeded`, `failed`, `planned` and the others of the run's
    state machine."""
    met_a_person: bool = False
    """Whether the step waited for a person at its boundary: an anchor, its own `ask`, its
    level."""
    answer: Answer | None = None
    """None for a step that did not leave the engine, or never reached the outside."""


class Recording(Value):
    format: Literal["taktus.recording/v1"] = FORMAT
    taken: Taken
    process: str = Field(min_length=1)
    process_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    cause: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any]
    """The limits the run ended with, a raised one included (a limits document)."""
    margin: float = Field(default=0.0, ge=0.0, le=0.9)
    prices: dict[str, Any] | None = None
    """The price table the instance computed money at, where it had one."""
    uncalibrated_margin: float | None = Field(default=None, ge=0.0)
    """What a worker without a calibration history reserved beyond its estimate on the
    instance (DEC-0034); None for the engine's default."""
    operations: tuple[Operation, ...] = ()
    """What each operation the run called was declared as: its effect, and the most one call
    consumes."""
    steps: tuple[Step, ...]

    def step(self, step_id: str) -> Step | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def answers(self, kind: Kind) -> list[tuple[Step, Answer]]:
        return [(s, s.answer) for s in self.steps if s.answer is not None and s.answer.kind == kind]


class UnreadableRecording(Exception):
    """The directory holds no recording this version reads; the message says why."""


def read(directory: Path) -> Recording:
    """The recording a directory holds."""
    path = directory / RECORDING
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise UnreadableRecording(f"{path}: {error.strerror or error}") from error
    except ValueError as error:
        raise UnreadableRecording(f"{path}: not JSON ({error})") from error
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise UnreadableRecording(f"{path}: not a recording in the format {FORMAT}")
    try:
        return Recording.model_validate(document)
    except ValueError as error:
        raise UnreadableRecording(f"{path}: {error}") from error


def write(directory: Path, recording: Recording, files: dict[str, bytes]) -> None:
    """Write the recording and the files it names. Each file is written as given; a result
    document is written as indented JSON, so that a change to it reads as a change."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    text = json.dumps(recording.document(), ensure_ascii=False, indent=2, sort_keys=True)
    (directory / RECORDING).write_text(text + "\n", encoding="utf-8")


def json_file(document: Any) -> bytes:
    """A result document as a recording keeps it."""
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
