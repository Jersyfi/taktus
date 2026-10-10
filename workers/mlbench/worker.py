#!/usr/bin/env python3
"""The `mlbench` worker: training, evaluation and prediction of classical models, behind the
worker contract v1.

It is the second proof case of the contract (ADR-0007): progress measured in epochs rather than
tool calls, compute held in a resource class, the result a model artifact with metrics. Three
operations, named by `task.inputs.operation`:

- `train` (the default) — read a labelled dataset, split off a held-out share, train a linear
  classifier one epoch per step, and return the model file with its metrics on the held-out rows.
  A step boundary and a checkpoint follow every epoch; a stop lands on one, and a resumed
  assignment continues from it to the same model as a run straight through.
- `evaluate` — measure a model file against a labelled dataset and return the metrics.
- `predict` — apply a model file to rows and return each row's class with its confidence.

The machine learning itself is `bench.py`; this file is the contract around it. It imports
nothing from src/taktus: it is a separate deployable, as every worker is.

Fault injection (`--fault NAME`) makes the worker violate exactly one conformance check, so that
the suite can be shown to catch it. `--list-faults` prints every fault with the check it breaks.

Credentials arrive as names. This worker reads whether they are present and nothing else, and
never writes a value anywhere — except under the three W-08 faults, which exist to be caught.
The execution adapter tells it where to listen and where its state lives (TAKTUS_UNIT_PORT,
TAKTUS_UNIT_STATE_DIR — the launch convention of the execution port).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The bench lives beside this file, in the image as in the repository.
import bench

type Json = dict[str, Any]

CONTRACT = "worker/v1"
VERSION = "0.1.0"  # this worker's own version, recorded in every model file and in provenance
NAME = "mlbench"
MAX_CONCURRENT = 2
AFTER_TIMEOUT = 60
FETCH_TIMEOUT = 60

READ, GENERATE = "data.read", "data.generate"
TRAIN, EVALUATE, PREDICT = "ml.train", "ml.evaluate", "ml.predict"
TOOLS = [READ, GENERATE, TRAIN, EVALUATE, PREDICT]
OPERATIONS = ("train", "evaluate", "predict")

# What a step is expected to cost, in compute seconds, before the estimate factor: a fixed part
# and a part per value read or passed over (rows times features). Rough on purpose — the
# estimate says `confidence: low` — and measured against the actual by the control plane.
FIXED_SECONDS = 0.05
SECONDS_PER_VALUE = 1e-7
ASSUMED_ROWS, ASSUMED_FEATURES = 10_000, 16  # a dataset behind a URI that declares neither

DEFAULT_DATASET: Json = {"synthetic": {"rows": 2000, "features": 8, "classes": 3}}

FAULTS: dict[str, str] = {
    "W-01": "capabilities declares no consumption kind",
    "W-02": "estimate answers 501 instead of an estimate",
    "W-03-gap": "the second event is skipped: seq jumps from 1 to 3",
    "W-03-resume": "Last-Event-ID and ?after= are ignored; the stream always replays from 1",
    "W-04": "consumption is reported for every step at the end, just before assignment.finished",
    "W-05": "no step.boundary is ever emitted, although checkpoints are still written",
    "W-06": "a stop skips the boundary of the running step and reports the previous checkpoint",
    "W-07": "a tool outside the frame is used and reported without refused: true",
    "W-08-event": "the value of the first credential is written into a step.progress message",
    "W-08-artifact": "the value of the first credential is written into an artifact",
    "W-08-log": "the value of the first credential is written to the worker's log",
    "W-09": "tool.called carries its arguments in clear instead of their sha256",
    "W-10": "an estimate above the limits is accepted; the assignment fails after its first step",
    "W-11": "a resumed assignment produces the artifacts from before its checkpoint again",
    "W-13": "a host outside allowed_hosts is reached and reported without refused: true",
    "W-14": "the limits are ignored once running: epochs start after the total crossed them",
    "W-15": "an assignment beyond max_concurrent_assignments is accepted instead of answered 503",
    "W-16": "the state of an id never received is answered 200, accepted, instead of 404",
    "W-17": "an assignment whose id is held is accepted again as a second one instead of 409",
    "W-18": "the task's command after the work is ignored: it never runs and nothing is published",
}


def check_of(fault: str) -> str:
    return fault[:4]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(message: str) -> None:
    sys.stderr.write(f"{now()} mlbench-worker {message}\n")
    sys.stderr.flush()


# --- the task -----------------------------------------------------------------------------------


class TaskError(Exception):
    """The task cannot be done as given; the assignment is rejected with this reason."""


@dataclass(frozen=True)
class Source:
    """Where a dataset or a model comes from: a URI the worker fetches, bytes in the task, or —
    for a dataset — the built-in generator. `digest`, where given, is checked on the bytes."""

    role: str  # "dataset" or "model"
    uri: str | None = None
    inline: bytes | None = None
    synthetic: Json | None = None
    digest: str | None = None
    rows: int | None = None
    features: int | None = None

    @property
    def tool(self) -> str:
        return GENERATE if self.synthetic is not None else READ

    @property
    def host(self) -> str | None:
        if self.uri is None:
            return None
        return (urlparse(self.uri).netloc or "").lower() or None

    @property
    def arguments(self) -> str:
        """What the tool is called with, as the text whose sha256 the event carries."""
        if self.uri is not None:
            return self.uri
        if self.synthetic is not None:
            return json.dumps(self.synthetic, sort_keys=True)
        return bench.sha256(self.inline or b"")

    def size(self) -> tuple[int, int]:
        """Rows and features, as far as they are known before reading."""
        if self.synthetic is not None:
            return int(self.synthetic.get("rows", 2000)), int(self.synthetic.get("features", 8))
        if self.inline is not None and self.rows is None:
            lines = self.inline.count(b"\n")
            first = self.inline.split(b"\n", 1)[0]
            return max(lines - 1, 1), max(first.count(b",") + 1, 1)
        return self.rows or ASSUMED_ROWS, self.features or ASSUMED_FEATURES


def source(role: str, given: Any) -> Source:
    if not isinstance(given, dict):
        raise TaskError(f"inputs.{role} is an object")
    digest = given.get("digest")
    if digest is not None and not (
        isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    ):
        raise TaskError(f"inputs.{role}.digest is sha256: and 64 hex characters")
    hints = {k: int(given[k]) for k in ("rows", "features") if isinstance(given.get(k), int)}
    if "uri" in given:
        uri = str(given["uri"])
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise TaskError(f"inputs.{role}.uri is an http or https URI")
        if "@" in parsed.netloc:
            raise TaskError(f"inputs.{role}.uri carries no credential")
        return Source(role, uri=uri, digest=digest, **hints)
    if "base64" in given:
        try:
            inline = base64.b64decode(str(given["base64"]), validate=True)
        except (binascii.Error, ValueError) as error:
            raise TaskError(f"inputs.{role}.base64 is not base64") from error
        if digest is not None and bench.sha256(inline) != digest:
            raise TaskError(f"the bytes of inputs.{role} do not match its digest")
        return Source(role, inline=inline, digest=digest, **hints)
    if "synthetic" in given and role == "dataset":
        spec = given["synthetic"]
        if not isinstance(spec, dict):
            raise TaskError("inputs.dataset.synthetic is an object")
        return Source(role, synthetic=dict(spec))
    raise TaskError(
        f"inputs.{role} names a uri or base64" + (", or synthetic" if role == "dataset" else "")
    )


@dataclass(frozen=True)
class Job:
    """The task read: which operation, on what, with which settings."""

    operation: str
    dataset: Source
    model: Source | None
    label: str | None
    seed: int
    epochs: int
    holdout: float

    @property
    def sources(self) -> list[Source]:
        return [s for s in (self.model, self.dataset) if s is not None]


def job_of(task: Json) -> Job:
    inputs = task.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise TaskError("task.inputs is an object")
    operation = str(inputs.get("operation", "train"))
    if operation not in OPERATIONS:
        raise TaskError(f"inputs.operation is one of {', '.join(OPERATIONS)}")
    model = None
    if operation != "train":
        if "model" not in inputs:
            raise TaskError(f"an {operation} assignment names its model under inputs.model")
        model = source("model", inputs["model"])
        if model.digest is None:
            raise TaskError("inputs.model names its digest: a model is used only as pinned")
    elif "dataset" not in inputs:
        inputs = {**inputs, "dataset": DEFAULT_DATASET}
    if "dataset" not in inputs:
        raise TaskError(f"an {operation} assignment names its rows under inputs.dataset")
    dataset = source("dataset", inputs["dataset"])
    seed, epochs, holdout = (
        inputs.get("seed", 0),
        inputs.get("epochs", 5),
        inputs.get("holdout", 0.2),
    )
    if not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise TaskError("inputs.seed is an integer from 0 to 2^32 - 1")
    if not isinstance(epochs, int) or not 1 <= epochs <= 10_000:
        raise TaskError("inputs.epochs is an integer from 1 to 10000")
    if not isinstance(holdout, int | float) or not 0.05 <= holdout <= 0.5:
        raise TaskError("inputs.holdout is a share from 0.05 to 0.5")
    label = inputs.get("label")
    if label is not None and not isinstance(label, str):
        raise TaskError("inputs.label names a column")
    return Job(operation, dataset, model, label, seed, epochs, float(holdout))


# --- plans --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedStep:
    step_id: str
    kind: str
    summary: str
    tool: str | None
    seconds: float  # expected compute seconds, before the estimate factor
    epoch: int | None = None
    argv: tuple[str, ...] | None = None  # the task's command after the work
    artifact: str | None = None  # the artifact the command after the work fills


def plan_for(task: Json, job: Job, floor: float) -> list[PlannedStep]:
    rows, width = job.dataset.size()
    values = rows * width
    load = FIXED_SECONDS + values * SECONDS_PER_VALUE
    steps = [PlannedStep("load", "load", f"read the {job.operation} inputs", None, load)]
    if job.operation == "train":
        per_epoch = max(floor, FIXED_SECONDS + values * SECONDS_PER_VALUE)
        steps += [
            PlannedStep(f"epoch-{k}", "epoch", f"epoch {k} of {job.epochs}", TRAIN, per_epoch, k)
            for k in range(1, job.epochs + 1)
        ]
        steps.append(
            PlannedStep(
                "evaluate",
                "evaluate",
                "measure on the held-out rows, write the model",
                EVALUATE,
                load,
            )
        )
    elif job.operation == "evaluate":
        steps.append(
            PlannedStep("evaluate", "evaluate", "measure the model on the rows", EVALUATE, load)
        )
    else:
        steps.append(
            PlannedStep("predict", "predict", "apply the model to the rows", PREDICT, load)
        )
    after = task.get("after")
    if isinstance(after, dict):
        steps.append(
            PlannedStep(
                "after",
                "shell",
                "the command after the work",
                None,
                0.0,
                argv=tuple(str(p) for p in after.get("command") or ()),
                artifact=str(after.get("artifact")),
            )
        )
    return steps


# --- state --------------------------------------------------------------------------------------


@dataclass
class Produced:
    artifact_id: str
    kind: str
    media_type: str
    content: bytes

    @property
    def digest(self) -> str:
        return bench.sha256(self.content)

    def describe(self, assignment_id: str) -> Json:
        return {
            "id": self.artifact_id,
            "kind": self.kind,
            "digest": self.digest,
            "media_type": self.media_type,
            "size_bytes": len(self.content),
            "uri": f"/v1/assignments/{assignment_id}/artifacts/{self.artifact_id}",
        }


@dataclass
class Assignment:
    body: Json
    job: Job | None
    plan: list[PlannedStep]
    start_index: int
    inherited: list[Produced]  # produced before the checkpoint this assignment resumes from
    work: Json = field(default_factory=dict)  # what the steps so far left for the next ones
    status: str = "accepted"
    outcome: str | None = None
    reason: str | None = None
    checkpoint_ref: str | None = None
    accepted_at: str = field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    events: list[Json] = field(default_factory=list)
    produced: list[Produced] = field(default_factory=list)
    stop_requested: bool = False
    seq: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    changed: threading.Condition = field(init=False)

    def __post_init__(self) -> None:
        self.changed = threading.Condition(self.lock)

    @property
    def id(self) -> str:
        return str(self.body["assignment_id"])

    def state(self) -> Json:
        state: Json = {
            "assignment_id": self.id,
            "status": self.status,
            "last_seq": self.seq,
            "accepted_at": self.accepted_at,
        }
        for key in ("outcome", "checkpoint_ref", "reason", "started_at", "finished_at"):
            if getattr(self, key) is not None:
                state[key] = getattr(self, key)
        return state


class StepFailed(Exception):
    """The step could not do its work; the assignment fails with this reason."""


class Worker:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.fault: str | None = options.fault
        self.resource_class: str = options.resource_class
        self.state_dir = Path(options.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.assignments: dict[str, Assignment] = {}
        self.lock = threading.Lock()

    # -- declarations --

    def capabilities(self) -> Json:
        kinds = [] if self.fault == "W-01" else ["compute"]
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "capabilities": list(TOOLS),
            "consumption": {"kinds": kinds, "resource_classes": [self.resource_class]},
            "supports": {
                "native_pause": False,
                "step_boundary_signal": True,
                "streaming_events": True,
                "estimate": True,
            },
            "max_concurrent_assignments": self.options.max_concurrent,
        }

    def plan(self, task: Json) -> tuple[Job, list[PlannedStep]]:
        job = job_of(task)
        plan = plan_for(task, job, self.options.epoch_floor)
        if self.fault == "W-18":
            plan = [s for s in plan if s.argv is None]
        return job, plan

    def expected(self, step: PlannedStep) -> float:
        return float(self.options.estimate_factor) * step.seconds

    def estimate(self, request: Json) -> Json:
        try:
            _, plan = self.plan(request.get("task", {}))
        except TaskError:
            plan = []
        start = self._resume_index(request.get("context", {}).get("checkpoint_ref"), plan)
        remaining = plan[start:]
        seconds = round(sum(self.expected(s) for s in remaining), 3)
        return {
            "confidence": "low",
            "compute_seconds": seconds,
            "resource_class": self.resource_class,
            "wall_seconds": int(seconds) + 1,
            "steps": len(remaining),
        }

    # -- checkpoints --

    def _path(self, ref: str, suffix: str) -> Path:
        return self.state_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", ref) + suffix)

    def _write_checkpoint(self, assignment: Assignment, index: int, step: PlannedStep) -> str:
        ref = f"ckpt/{assignment.id}/{step.step_id}"
        produced = assignment.inherited + assignment.produced
        record = {
            "assignment_id": assignment.id,
            "index": index,
            "plan": [s.step_id for s in assignment.plan],
            "work": assignment.work,
            "produced": [
                {
                    "artifact_id": p.artifact_id,
                    "kind": p.kind,
                    "media_type": p.media_type,
                    "content": base64.b64encode(p.content).decode(),
                }
                for p in produced
            ],
        }
        self._path(ref, ".json").write_text(json.dumps(record), encoding="utf-8")
        return ref

    def _load_checkpoint(self, ref: str) -> Json | None:
        path = self._path(ref, ".json")
        if not path.is_file():
            return None
        result: Json = json.loads(path.read_text(encoding="utf-8"))
        return result

    def _resume_index(self, ref: str | None, plan: list[PlannedStep]) -> int:
        if not ref:
            return 0
        record = self._load_checkpoint(ref)
        if record is None or record.get("plan") != [s.step_id for s in plan]:
            return 0
        return int(record["index"]) + 1

    # -- assignments --

    def accept(self, body: Json) -> tuple[int, Json]:
        """Record an assignment: 201 with its state, or a problem."""
        problem = validate_assignment(body)
        if problem:
            return 400, {"title": "invalid assignment", "status": 400, "detail": problem}
        assignment_id = str(body["assignment_id"])
        with self.lock:
            if assignment_id in self.assignments and self.fault != "W-17":
                return 409, {"title": "assignment exists", "status": 409}
            running = sum(1 for a in self.assignments.values() if a.status != "finished")
            if running >= self.options.max_concurrent and self.fault != "W-15":
                return 503, {"title": "at capacity", "status": 503}
            rejection: str | None = None
            job: Job | None = None
            plan: list[PlannedStep] = []
            try:
                job, plan = self.plan(body["task"])
            except TaskError as error:
                rejection = str(error)
            inherited: list[Produced] = []
            work: Json = {}
            start = 0
            ref = body.get("context", {}).get("checkpoint_ref")
            if ref and rejection is None:
                record = self._load_checkpoint(ref)
                if record is None:
                    rejection = f"unknown checkpoint {ref}"
                elif record.get("plan") != [s.step_id for s in plan]:
                    rejection = f"checkpoint {ref} belongs to a different plan"
                else:
                    start = int(record["index"]) + 1
                    work = dict(record.get("work") or {})
                    inherited = [
                        Produced(
                            p["artifact_id"],
                            p["kind"],
                            p["media_type"],
                            base64.b64decode(p["content"]),
                        )
                        for p in record["produced"]
                    ]
            assignment = Assignment(body, job, plan, start, inherited, work)
            if rejection is None:
                rejection = self._does_not_fit(body, plan[start:])
            self.assignments[assignment_id] = assignment
            if rejection is not None:
                self._reject(assignment, rejection)
                return 201, assignment.state()
        threading.Thread(target=self._run, args=(assignment,), daemon=True).start()
        return 201, assignment.state()

    def _does_not_fit(self, body: Json, remaining: list[PlannedStep]) -> str | None:
        estimate = self.estimate(body)
        limits = body["limits"]
        if self.fault != "W-10":
            compute = limits.get("compute")
            if compute is None:
                return "this worker consumes compute, and the limits carry no compute limit"
            if compute.get("resource_class") != self.resource_class:
                return (
                    f"limits.compute.resource_class {compute.get('resource_class')!r} is not "
                    f"this worker's {self.resource_class!r}"
                )
            if estimate["compute_seconds"] > compute["seconds"]:
                return (
                    f"estimated {estimate['compute_seconds']}s of {self.resource_class} exceeds "
                    f"the limit of {compute['seconds']}s"
                )
        frame = body["frame"]
        if len(remaining) > frame["max_steps"]:
            return f"{len(remaining)} steps needed, frame allows {frame['max_steps']}"
        deadline = frame.get("deadline")
        if deadline:
            try:
                until = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            except ValueError:
                return f"deadline {deadline!r} is not a date-time"
            if until.timestamp() < time.time() + estimate["wall_seconds"]:
                return f"the deadline {deadline} is before the estimated end"
        return None

    def _reject(self, assignment: Assignment, reason: str) -> None:
        with assignment.lock:
            assignment.status = "finished"
            assignment.outcome = "rejected"
            assignment.reason = reason
            assignment.finished_at = now()
            self._emit(
                assignment, {"type": "assignment.finished", "outcome": "rejected", "reason": reason}
            )
        log(f"assignment {assignment.id} rejected: {reason}")

    def stop(self, assignment: Assignment, request: Json) -> Json:
        with assignment.lock:
            if assignment.status != "finished":
                assignment.stop_requested = True
                assignment.status = "stopping"
            return assignment.state()

    # -- the run --

    def _emit(self, assignment: Assignment, event: Json) -> Json:
        """Append one event. Caller holds the assignment's lock."""
        assignment.seq += 1
        if self.fault == "W-03-gap" and assignment.seq == 2:
            assignment.seq = 3
        full = {"assignment_id": assignment.id, "seq": assignment.seq, "ts": now(), **event}
        assignment.events.append(full)
        assignment.changed.notify_all()
        return full

    def _emit_locked(self, assignment: Assignment, event: Json) -> None:
        with assignment.lock:
            self._emit(assignment, event)

    def _call(
        self,
        assignment: Assignment,
        step: PlannedStep,
        tool: str,
        arguments: str,
        host: str | None = None,
    ) -> str | None:
        """Emit the tool.called of one use of a tool, held against the frame where the call
        happens: None when the tool may be used, else why it was refused."""
        frame = assignment.body["frame"]
        digest = arguments if self.fault == "W-09" else bench.sha256(arguments.encode())
        call: Json = {
            "type": "tool.called",
            "step_id": step.step_id,
            "tool": tool,
            "arguments_digest": digest,
        }
        if host is not None:
            call["host"] = host
        refusal: str | None = None
        if tool not in frame.get("allowed_tools", []) and self.fault != "W-07":
            refusal = f"{tool} is outside the frame's allowed_tools"
        elif (
            host is not None
            and host not in (frame.get("allowed_hosts") or [])
            and self.fault != "W-13"
        ):
            refusal = f"{host} is not in the frame's allowed_hosts"
        if refusal is not None:
            call["refused"] = True
            call["reason"] = refusal
        self._emit_locked(assignment, call)
        return refusal

    def _run(self, assignment: Assignment) -> None:
        credential = self._first_credential(assignment.body)
        deferred: list[Json] = []
        used = 0.0  # compute seconds this assignment has consumed: its running total
        last_checkpoint: str | None = assignment.body.get("context", {}).get("checkpoint_ref")
        with assignment.lock:
            assignment.status = "running"
            assignment.started_at = now()
            if self.fault == "W-11":
                for produced in assignment.inherited:
                    assignment.produced.append(produced)
                    self._emit(assignment, self._artifact_event(assignment, produced, None))
        log(f"assignment {assignment.id} started at step {assignment.start_index + 1}")
        for index in range(assignment.start_index, len(assignment.plan)):
            step = assignment.plan[index]
            began = time.monotonic()
            self._emit_locked(
                assignment,
                {
                    "type": "step.started",
                    "step_id": step.step_id,
                    "kind": step.kind,
                    "summary": step.summary,
                },
            )
            failure: str | None = None
            try:
                self._do(assignment, step, credential)
            except StepFailed as error:
                failure = str(error)
            if self.fault == "W-08-log" and credential:
                log(f"credential {credential[0]}={credential[1]}")  # the W-08-log fault
            if self.fault == "W-08-event" and credential:
                self._emit_locked(
                    assignment,
                    {
                        "type": "step.progress",
                        "step_id": step.step_id,
                        "message": f"using {credential[0]}={credential[1]}",  # the W-08 fault
                    },
                )
            if step.epoch is not None and failure is None:
                remaining = self.options.epoch_floor - (time.monotonic() - began)
                if remaining > 0:
                    time.sleep(remaining)  # the epoch holds its place for the floor's length
            consumption: Json = {
                "type": "consumption.reported",
                "step_id": step.step_id,
                "compute_seconds": round(max(time.monotonic() - began, 0.001), 3),
                "resource_class": self.resource_class,
            }
            used += consumption["compute_seconds"]
            with assignment.lock:
                if self.fault == "W-04":
                    deferred.append(consumption)
                else:
                    self._emit(assignment, consumption)
                skip_boundary = self.fault == "W-06" and assignment.stop_requested
                checkpoint = self._write_checkpoint(assignment, index, step)
                if self.fault != "W-05" and not skip_boundary:
                    self._emit(
                        assignment,
                        {
                            "type": "step.boundary",
                            "step_id": step.step_id,
                            "checkpoint_ref": checkpoint,
                        },
                    )
                if not skip_boundary:
                    last_checkpoint = checkpoint
                if failure is not None:
                    self._finish(assignment, "failed", reason=failure)
                    return
                if self.fault == "W-10" and index == assignment.start_index:
                    excess = self._limit_excess(assignment.body)
                    if excess:
                        self._finish(assignment, "failed", reason=excess)
                        return
                if assignment.stop_requested:
                    self._finish(assignment, "stopped", checkpoint_ref=last_checkpoint)
                    return
                following = index + 1 < len(assignment.plan)
                if following and self.fault != "W-14":
                    halt = self._over_ceiling(assignment.body, used, assignment.plan[index + 1])
                    if halt is not None:
                        self._finish(
                            assignment,
                            "stopped",
                            reason=halt,
                            checkpoint_ref=last_checkpoint,
                            limit="compute",
                        )
                        return
        with assignment.lock:
            for consumption in deferred:
                self._emit(assignment, consumption)
            self._finish(
                assignment,
                "succeeded",
                summary=f"{len(assignment.plan) - assignment.start_index} step(s) completed",
            )

    # -- the steps --

    def _do(
        self, assignment: Assignment, step: PlannedStep, credential: tuple[str, str] | None
    ) -> None:
        job = assignment.job
        if job is None:  # a rejected assignment never runs
            raise StepFailed("the task could not be read")
        if step.argv is not None:
            output, failure = run_after(step.argv)
            if failure is not None:
                raise StepFailed(failure)
            self._produce(
                assignment, step, str(step.artifact), "output", "text/plain", output, None
            )
            return
        if step.kind == "load":
            self._load(assignment, step, job)
            return
        if step.tool is None:
            raise StepFailed(f"step {step.step_id!r} names no tool")
        refusal = self._call(
            assignment,
            step,
            step.tool,
            json.dumps({"step": step.step_id, "seed": job.seed}, sort_keys=True),
        )
        if refusal is not None:
            raise StepFailed(
                f"step {step.step_id!r} needs {step.tool}, which the frame does not allow: "
                f"{refusal}"
            )
        try:
            if step.kind == "epoch":
                self._epoch(assignment, step, job, credential)
            elif job.operation == "train":
                self._finish_training(assignment, step, job, credential)
            elif job.operation == "evaluate":
                model, x, y = self._held(assignment)
                if y is None:
                    raise StepFailed(
                        "an evaluation needs the label column the model was trained on"
                    )
                metrics = bench.evaluate(model, x, y)
                self._produce(
                    assignment,
                    step,
                    "metrics",
                    "report",
                    "application/json",
                    _json_bytes(metrics),
                    credential,
                )
            else:
                model, x, _ = self._held(assignment)
                classes, confidence = bench.predict(model, x)
                self._produce(
                    assignment,
                    step,
                    "predictions",
                    "dataset",
                    "text/csv",
                    bench.predictions_csv(classes, confidence),
                    credential,
                )
        except bench.BenchError as error:
            raise StepFailed(str(error)) from error

    def _load(self, assignment: Assignment, step: PlannedStep, job: Job) -> None:
        """Read every source the task names — each one a tool call, held against the frame —
        and keep what the following steps need in the state directory."""
        read: dict[str, bytes] = {}
        for src in job.sources:
            refusal = self._call(assignment, step, src.tool, src.arguments, src.host)
            if refusal is not None:
                raise StepFailed(
                    f"step 'load' needs the {src.role} from {src.host or src.tool}, which the "
                    f"frame does not allow: {refusal}"
                )
        for src in job.sources:
            read[src.role] = self._read(src, job.seed)
        try:
            if job.operation == "train":
                table = bench.parse_csv(read["dataset"], job.label, require_label=True)
                prepared = bench.prepare(table, job.seed, job.holdout)
                data = self._path(f"data/{assignment.id}", ".npz")
                np.savez(
                    data,
                    x_train=prepared.x_train,
                    y_train=prepared.y_train,
                    x_holdout=prepared.x_holdout,
                    y_holdout=prepared.y_holdout,
                    mean=prepared.mean,
                    scale=prepared.scale,
                )
                assignment.work = {
                    "data": data.name,
                    "features": list(prepared.features),
                    "label": prepared.label,
                    "classes": list(prepared.classes),
                    "digest": prepared.digest,
                    "rows": prepared.rows,
                    "state": None,
                }
                message = (
                    f"{prepared.rows} rows, {len(prepared.features)} features, "
                    f"{len(prepared.classes)} classes; {len(prepared.y_holdout)} held out"
                )
            else:
                model = bench.load_model(read["model"])
                table = bench.parse_csv(read["dataset"], model.label, require_label=False)
                x = bench.columns(model, table)
                data = self._path(f"data/{assignment.id}", ".npz")
                arrays = {"x": x} if table.y is None else {"x": x, "y": table.y}
                np.savez(data, **arrays)
                assignment.work = {
                    "data": data.name,
                    "model": base64.b64encode(read["model"]).decode(),
                }
                message = f"{x.shape[0]} rows for a model of {len(model.classes)} classes"
        except bench.BenchError as error:
            raise StepFailed(str(error)) from error
        self._emit_locked(
            assignment, {"type": "step.progress", "step_id": step.step_id, "message": message}
        )

    def _read(self, src: Source, seed: int) -> bytes:
        if src.synthetic is not None:
            try:
                data, _ = bench.synthetic(src.synthetic, seed)
            except bench.BenchError as error:
                raise StepFailed(str(error)) from error
        elif src.inline is not None:
            data = src.inline
        else:
            data = fetch(str(src.uri), self.options.max_bytes)
        if src.digest is not None and bench.sha256(data) != src.digest:
            raise StepFailed(
                f"the {src.role} read from {src.host or 'the task'} does not match the digest "
                "the task names; nothing was used"
            )
        return data

    def _prepared(self, assignment: Assignment) -> bench.Prepared:
        work = assignment.work
        with np.load(self.state_dir / work["data"], allow_pickle=False) as arrays:
            return bench.Prepared(
                tuple(work["features"]),
                str(work["label"]),
                tuple(work["classes"]),
                arrays["mean"],
                arrays["scale"],
                arrays["x_train"],
                arrays["y_train"],
                arrays["x_holdout"],
                arrays["y_holdout"],
                str(work["digest"]),
                int(work["rows"]),
            )

    def _held(self, assignment: Assignment) -> tuple[bench.Model, np.ndarray, np.ndarray | None]:
        work = assignment.work
        model = bench.load_model(base64.b64decode(work["model"]))
        with np.load(self.state_dir / work["data"], allow_pickle=False) as arrays:
            return model, arrays["x"], arrays["y"] if "y" in arrays else None

    def _epoch(
        self,
        assignment: Assignment,
        step: PlannedStep,
        job: Job,
        credential: tuple[str, str] | None,
    ) -> None:
        epoch = step.epoch or 0
        data = self._prepared(assignment)
        state, loss = bench.epoch(data, job.seed, assignment.work.get("state"))
        assignment.work = {**assignment.work, "state": state}
        self._emit_locked(
            assignment,
            {
                "type": "step.progress",
                "step_id": step.step_id,
                "message": f"epoch {epoch} of {job.epochs}: training loss {loss:.6f}",
                "progress": {"current": epoch, "total": job.epochs, "unit": "epochs"},
            },
        )
        snapshot = bench.model_file(
            data, state, seed=job.seed, epochs=epoch, worker=self._identity(), metrics=None
        )
        self._produce(
            assignment,
            step,
            f"checkpoint-{epoch}",
            "model.checkpoint",
            "application/json",
            snapshot,
            credential,
        )

    def _finish_training(
        self,
        assignment: Assignment,
        step: PlannedStep,
        job: Job,
        credential: tuple[str, str] | None,
    ) -> None:
        """The model file, measured on the held-out rows through the function that serves it:
        what is evaluated is the file as written, not the classifier in memory."""
        data = self._prepared(assignment)
        state = assignment.work.get("state")
        if state is None:
            raise StepFailed("no epoch has run, so there is no model to evaluate")
        unmeasured = bench.model_file(
            data, state, seed=job.seed, epochs=job.epochs, worker=self._identity(), metrics=None
        )
        metrics = bench.evaluate(bench.load_model(unmeasured), data.x_holdout, data.y_holdout)
        model = bench.model_file(
            data, state, seed=job.seed, epochs=job.epochs, worker=self._identity(), metrics=metrics
        )
        self._produce(
            assignment,
            step,
            "metrics",
            "report",
            "application/json",
            _json_bytes(metrics),
            credential,
        )
        self._produce(assignment, step, "model", "model", "application/json", model, None)

    def _identity(self) -> Json:
        return {"worker": NAME, "version": VERSION}

    def _over_ceiling(self, body: Json, used: float, following: PlannedStep) -> str | None:
        """The limits are this worker's hard ceiling (W-14): the next step does not start when
        the running total plus that step's expected demand would exceed the compute limit."""
        compute = body["limits"].get("compute") or {}
        if compute.get("resource_class") != self.resource_class:
            return None
        ceiling = float(compute["seconds"])
        expected = self.expected(following)
        if used >= ceiling or used + expected > ceiling:
            return (
                f"the running total of {used:.3f}s of {self.resource_class} and the "
                f"{expected:.3f}s step {following.step_id!r} expects would exceed the limit of "
                f"{ceiling:g}s; halted at the boundary"
            )
        return None

    def _limit_excess(self, body: Json) -> str | None:
        estimate = self.estimate(body)
        compute = body["limits"].get("compute") or {}
        if estimate["compute_seconds"] > compute.get("seconds", float("inf")):
            return f"limits exceeded after starting: estimated {estimate['compute_seconds']}s"
        return None

    def _produce(
        self,
        assignment: Assignment,
        step: PlannedStep,
        artifact_id: str,
        kind: str,
        media_type: str,
        content: bytes,
        credential: tuple[str, str] | None,
    ) -> None:
        if self.fault == "W-08-artifact" and credential:
            content += f"\n{credential[0]}={credential[1]}\n".encode()  # the W-08 fault
        produced = Produced(artifact_id, kind, media_type, content)
        with assignment.lock:
            assignment.produced.append(produced)
            self._emit(assignment, self._artifact_event(assignment, produced, step.step_id))

    @staticmethod
    def _artifact_event(assignment: Assignment, produced: Produced, step_id: str | None) -> Json:
        event: Json = {"type": "artifact.produced", **produced.describe(assignment.id)}
        event["artifact_id"] = event.pop("id")
        if step_id is not None:
            event["step_id"] = step_id
        return event

    def _finish(
        self,
        assignment: Assignment,
        outcome: str,
        *,
        reason: str | None = None,
        checkpoint_ref: str | None = None,
        summary: str | None = None,
        limit: str | None = None,
    ) -> None:
        """Caller holds the assignment's lock."""
        event: Json = {"type": "assignment.finished", "outcome": outcome}
        if reason is not None:
            event["reason"] = reason
        if checkpoint_ref is not None:
            event["checkpoint_ref"] = checkpoint_ref
        if limit is not None:
            event["limit"] = limit
        if summary is not None:
            event["summary"] = summary
        assignment.status = "finished"
        assignment.outcome = outcome
        assignment.reason = reason
        assignment.checkpoint_ref = checkpoint_ref
        assignment.finished_at = now()
        self._emit(assignment, event)
        log(f"assignment {assignment.id} finished: {outcome}")

    @staticmethod
    def _first_credential(body: Json) -> tuple[str, str] | None:
        """Name and value of the first credential whose value the environment carries. The value
        is used by the W-08 faults only; the honest path logs presence, never a value."""
        for reference in body.get("credentials", []):
            name = reference.get("name")
            if reference.get("injected_as") == "env" and name in os.environ:
                log(f"credential {name}: present")
                return name, os.environ[name]
            log(f"credential {name}: absent")
        return None


def _json_bytes(document: Json) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fetch(uri: str, limit: int) -> bytes:
    """The bytes behind an http or https URI, at most `limit` of them."""
    request = urllib.request.Request(uri, headers={"User-Agent": f"taktus-{NAME}/{VERSION}"})  # noqa: S310 — the scheme is checked when the task is read
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:  # noqa: S310
            data: bytes = response.read(limit + 1)
    except (urllib.error.URLError, OSError) as error:
        raise StepFailed(f"{urlparse(uri).netloc} could not be read: {error}") from error
    if len(data) > limit:
        raise StepFailed(f"{urlparse(uri).netloc} returned more than {limit} bytes")
    return data


def run_after(argv: tuple[str, ...]) -> tuple[bytes, str | None]:
    """Run the task's command after the work: a program and its arguments, without a shell,
    with no credential in its environment (contracts/worker/v1 §3)."""
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
    environment = {k: os.environ[k] for k in keep if k in os.environ}
    try:
        completed = subprocess.run(  # noqa: S603 — the task's own command, by design
            list(argv),
            capture_output=True,
            timeout=AFTER_TIMEOUT,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return b"", f"the command after the work exceeded {AFTER_TIMEOUT}s"
    except OSError as error:
        return b"", f"the command after the work could not be started: {error.strerror}"
    if completed.returncode != 0:
        return completed.stdout, f"the command after the work exited with {completed.returncode}"
    return completed.stdout, None


def validate_assignment(body: Any) -> str | None:
    """The shape this worker needs. Full validation is the conformance suite's job; this keeps
    a malformed body from becoming a crash."""
    if not isinstance(body, dict):
        return "body is not an object"
    assignment_id = body.get("assignment_id")
    if not isinstance(assignment_id, str) or not re.match(
        r"^asg_[A-Za-z0-9_-]{4,}$", assignment_id
    ):
        return "assignment_id is missing or malformed"
    task = body.get("task")
    if not isinstance(task, dict) or not isinstance(task.get("goal"), str):
        return "task.goal is missing"
    frame = body.get("frame")
    if not isinstance(frame, dict) or not isinstance(frame.get("allowed_tools"), list):
        return "frame.allowed_tools is missing"
    if not isinstance(frame.get("max_steps"), int):
        return "frame.max_steps is missing"
    if not isinstance(body.get("limits"), dict) or not body["limits"]:
        return "limits is missing or empty"
    if body.get("callback", {}).get("events") != "sse":
        return "callback.events must be sse"
    return None


# --- http ---------------------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    worker: Worker  # set by main()

    def log_message(self, format: str, *args: Any) -> None:
        log(f"{self.address_string()} {format % args}")

    def _json(self, status: int, body: Json, content_type: str = "application/json") -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _problem(self, status: int, title: str, detail: str | None = None) -> None:
        body: Json = {"title": title, "status": status}
        if detail:
            body["detail"] = detail
        self._json(status, body, "application/problem+json")

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except ValueError:
            return None

    def _assignment(self, assignment_id: str) -> Assignment | None:
        assignment = self.worker.assignments.get(assignment_id)
        if assignment is None:
            self._problem(404, "no such assignment")
        return assignment

    def do_GET(self) -> None:
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        if parts == ["v1", "capabilities"]:
            self._json(200, self.worker.capabilities())
        elif parts == ["v1", "health"]:
            running = sum(1 for a in self.worker.assignments.values() if a.status != "finished")
            if running < self.worker.options.max_concurrent:
                self._json(200, {"status": "ready"})
            else:
                self._json(503, {"status": "not_ready", "detail": "at capacity"})
        elif len(parts) == 3 and parts[:2] == ["v1", "assignments"]:
            if self.worker.fault == "W-16" and parts[2] not in self.worker.assignments:
                # the W-16 fault: an id never received is answered as if it were held
                self._json(200, {"assignment_id": parts[2], "status": "accepted", "last_seq": 0})
            elif (assignment := self._assignment(parts[2])) is not None:
                with assignment.lock:
                    self._json(200, assignment.state())
        elif len(parts) == 4 and parts[:2] == ["v1", "assignments"] and parts[3] == "events":
            if (assignment := self._assignment(parts[2])) is not None:
                self._stream(assignment, url.query)
        elif len(parts) == 4 and parts[:2] == ["v1", "assignments"] and parts[3] == "artifacts":
            if (assignment := self._assignment(parts[2])) is not None:
                with assignment.lock:
                    artifacts = [p.describe(assignment.id) for p in assignment.produced]
                self._json(200, {"assignment_id": assignment.id, "artifacts": artifacts})
        elif len(parts) == 5 and parts[:2] == ["v1", "assignments"] and parts[3] == "artifacts":
            if (assignment := self._assignment(parts[2])) is not None:
                with assignment.lock:
                    found = [p for p in assignment.produced if p.artifact_id == parts[4]]
                if not found:
                    self._problem(404, "no such artifact")
                    return
                self.send_response(200)
                self.send_header("Content-Type", found[0].media_type)
                self.send_header("Content-Length", str(len(found[0].content)))
                self.end_headers()
                self.wfile.write(found[0].content)
        else:
            self._problem(404, "no such route")

    def do_POST(self) -> None:
        parts = urlparse(self.path).path.strip("/").split("/")
        body = self._body()
        if parts == ["v1", "estimate"]:
            if self.worker.fault == "W-02":
                self._problem(501, "estimate not implemented")  # the W-02 fault
            elif not isinstance(body, dict) or "task" not in body or "frame" not in body:
                self._problem(400, "invalid estimate request", "task and frame are required")
            else:
                self._json(200, self.worker.estimate(body))
        elif parts == ["v1", "assignments"]:
            status, response = self.worker.accept(body)
            if status == 201:
                self._json(201, response)
            else:
                self._json(status, response, "application/problem+json")
        elif len(parts) == 4 and parts[:2] == ["v1", "assignments"] and parts[3] == "stop":
            if (assignment := self._assignment(parts[2])) is not None:
                request = body if isinstance(body, dict) else {}
                self._json(202, self.worker.stop(assignment, request))
        else:
            self._problem(404, "no such route")

    def _stream(self, assignment: Assignment, query: str) -> None:
        after = 0
        header = self.headers.get("Last-Event-ID")
        param = parse_qs(query).get("after", [None])[0]
        for candidate in (header, param):
            if candidate is not None and candidate.isdigit():
                after = max(after, int(candidate))
        if self.worker.fault == "W-03-resume":
            after = 0  # the W-03-resume fault
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        sent = after
        try:
            while True:
                with assignment.lock:
                    pending = [e for e in assignment.events if e["seq"] > sent]
                    finished = assignment.status == "finished"
                    if not pending and not finished:
                        assignment.changed.wait(timeout=1.0)
                        continue
                for event in pending:
                    self._chunk(
                        f"id: {event['seq']}\nevent: {event['type']}\n"
                        f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                    )
                    sent = event["seq"]
                if finished and not pending:
                    break
                if pending and pending[-1]["type"] == "assignment.finished":
                    break
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _chunk(self, text: str) -> None:
        data = text.encode()
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()


# --- main -------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    port = int(os.environ.get("TAKTUS_UNIT_PORT") or 9000)
    state_dir = os.environ.get("TAKTUS_UNIT_STATE_DIR") or None
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument("--fault", choices=sorted(FAULTS), help="violate exactly one check")
    parser.add_argument("--list-faults", action="store_true", help="print the faults and exit")
    parser.add_argument("--state-dir", default=state_dir, help="checkpoints and prepared data")
    parser.add_argument("--resource-class", default="cpu.small", help="the class reported")
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=MAX_CONCURRENT,
        help="assignments held at once; a further one is answered 503, at capacity",
    )
    parser.add_argument(
        "--epoch-floor",
        type=float,
        default=0.0,
        help="seconds an epoch holds its place at least; the conformance gate sets it so that "
        "a stop can land while a training runs",
    )
    parser.add_argument(
        "--estimate-factor",
        type=float,
        default=1.0,
        help="the estimate is this factor times the expected demand; below 1 the worker "
        "underestimates, which makes the halt at a limit (W-14) observable",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=256 * 1024 * 1024,
        help="the most a dataset or a model read from a URI may hold",
    )
    args = parser.parse_args(argv)
    if args.estimate_factor <= 0:
        parser.error("--estimate-factor must be above 0")
    if args.max_concurrent < 1:
        parser.error("--max-concurrent must be at least 1")
    if args.epoch_floor < 0:
        parser.error("--epoch-floor must not be negative")
    if args.state_dir is None:
        args.state_dir = str(
            Path.home() / ".cache" / "taktus-mlbench-worker" / secrets.token_hex(4)
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_faults:
        for name, description in FAULTS.items():
            print(f"{name}\t{check_of(name)}\t{description}")
        return 0
    Handler.worker = Worker(args)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    fault = f", fault {args.fault}" if args.fault else ""
    log(f"listening on http://{args.host}:{server.server_port}{fault}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
