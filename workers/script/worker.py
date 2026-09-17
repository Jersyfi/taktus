#!/usr/bin/env python3
"""The `script` worker: a shell wrapper with no AI at all, behind the worker contract v1.

ADR-0007 makes this worker mandatory: a contract a shell script cannot satisfy is built around one
specific coding agent. Everything the contract asks for is here — capabilities, estimate,
assignment, a resumable event stream, consumption per step, step boundaries with checkpoints, a
stop that lands on a boundary, refusal of tools outside the frame, rejection before start when the
limits do not fit, artifacts, health — in one file that needs nothing but Python's standard
library. Run it: `python3 workers/script/worker.py --port 9000`.

Two profiles (`--profile`):

- `quick` — seconds of runtime, four steps, cpu consumption only. The everyday shape.
- `longrun` — the SHAPE of a training job: many steps, progress in epochs, `compute` consumption
  with a resource class, a checkpoint artifact per epoch and a model file at the end. It trains
  nothing and holds no accelerator; the resource class it reports is whatever it was started
  with. The real ML bench is a different worker, `mlbench`, planned for 0.4.0. This profile is
  evidence that the contract fits that shape, not that training works.

Fault injection (`--fault NAME`) makes the worker violate exactly one conformance check, so that
the suite can be shown to catch it. `--list-faults` prints every fault with the check it breaks.

Credentials arrive as names; the execution adapter puts the values into this process's
environment. This worker reads whether they are present and nothing else, and never writes a
value anywhere — except under the three W-08 faults, which exist to be caught. The same
adapter tells this worker where to listen and where its state lives (TAKTUS_UNIT_PORT,
TAKTUS_UNIT_STATE_DIR — the launch convention of the execution port), so that it can be
started as a process or as a container without further arguments.

This file imports nothing from src/taktus. It is a separate deployable, as every worker is.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

type Json = dict[str, Any]

CONTRACT = "worker/v1"
VERSION = "1.1.0"  # this worker's own version, recorded in the provenance of what it produces
TOOL = "shell.script"
MAX_CONCURRENT = 4
COMMAND_TIMEOUT = 60

FAULTS: dict[str, str] = {
    "W-01": "capabilities declares no consumption kind",
    "W-02": "estimate answers 501 instead of an estimate",
    "W-03-gap": "the second event is skipped: seq jumps from 1 to 3",
    "W-03-resume": "Last-Event-ID and ?after= are ignored; the stream always replays from 1",
    "W-04": "consumption is reported for every step at the end, just before assignment.finished",
    "W-05": "no step.boundary is ever emitted, although checkpoints are still written",
    "W-06": "a stop skips the boundary of the running step and reports the previous checkpoint",
    "W-07": "a tool outside the frame is executed and reported without refused: true",
    "W-08-event": "the value of the first credential is written into a step.progress message",
    "W-08-artifact": "the value of the first credential is written into an artifact",
    "W-08-log": "the value of the first credential is written to the worker's log",
    "W-09": "tool.called carries the command in clear instead of its sha256",
    "W-10": "an estimate above the limits is accepted; the assignment fails after its first step",
    "W-11": "a resumed assignment produces the artifacts from before its checkpoint again",
    "W-13": "a host outside allowed_hosts is reached and reported without refused: true",
}


def check_of(fault: str) -> str:
    return fault[:4]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(message: str) -> None:
    sys.stderr.write(f"{now()} script-worker {message}\n")
    sys.stderr.flush()


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- plans -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    kind: str
    media_type: str
    content: bytes | None = None  # None: the command's output


@dataclass(frozen=True)
class PlannedStep:
    step_id: str
    kind: str
    summary: str
    command: str
    seconds: float
    artifacts: tuple[ArtifactSpec, ...] = ()
    progress: tuple[int, int] | None = None  # (current, total) in epochs


def quick_plan(step_seconds: float) -> list[PlannedStep]:
    return [
        PlannedStep("inspect", "shell", "inspect the host", "uname -sm", step_seconds),
        PlannedStep(
            "prepare",
            "shell",
            "write the plan",
            "printf 'plan: inspect, prepare, run, report\\n'",
            step_seconds,
            (ArtifactSpec("plan", "plan", "text/plain"),),
        ),
        PlannedStep("run", "shell", "compute the answer", "expr 6 '*' 7", step_seconds),
        PlannedStep(
            "report",
            "shell",
            "write the result",
            "printf 'result: 42\\n'",
            step_seconds,
            (ArtifactSpec("result", "report", "text/plain"),),
        ),
    ]


def longrun_plan(epochs: int, epoch_seconds: float) -> list[PlannedStep]:
    steps = [
        PlannedStep(
            "load", "load", "load and split the dataset", "printf 'rows=1000 features=8\\n'", 0.2
        )
    ]
    for k in range(1, epochs + 1):
        loss = round(1.0 / (k + 1), 3)
        steps.append(
            PlannedStep(
                f"epoch-{k}",
                "epoch",
                f"epoch {k} of {epochs}",
                f"printf 'epoch {k} loss {loss}\\n'",
                epoch_seconds,
                (ArtifactSpec(f"checkpoint-{k}", "model.checkpoint", "text/plain"),),
                (k, epochs),
            )
        )
    model = b"".join(hashlib.sha256(f"weights-{k}".encode()).digest() for k in range(epochs))
    steps.append(
        PlannedStep(
            "evaluate",
            "evaluate",
            "evaluate on the held-out split and write the model",
            'printf \'{"accuracy": 0.97, "epochs": %d}\\n\' ' + str(epochs),
            0.2,
            (
                ArtifactSpec("metrics", "report", "application/json"),
                ArtifactSpec("model", "model", "application/octet-stream", model),
            ),
        )
    )
    return steps


def plan_for(task: Json, profile: str, options: argparse.Namespace) -> list[PlannedStep]:
    """The steps of an assignment: the commands the task carries, else the profile's."""
    commands = task.get("inputs", {}).get("commands")
    if isinstance(commands, list) and commands and all(isinstance(c, str) for c in commands):
        return [
            PlannedStep(
                f"cmd-{n}",
                "shell",
                command[:80],
                command,
                options.step_seconds,
                (ArtifactSpec(f"output-{n}", "log", "text/plain"),),
            )
            for n, command in enumerate(commands, 1)
        ]
    if profile == "longrun":
        return longrun_plan(options.epochs, options.epoch_seconds)
    return quick_plan(options.step_seconds)


# --- state -----------------------------------------------------------------------------------


def outside_frame(tool: str, frame: Json) -> bool:
    return tool not in frame.get("allowed_tools", [])


def host_outside_frame(host: str, frame: Json) -> bool:
    """An absent or empty allowed_hosts allows no host at all: the affirmative list is the
    whole of what may be reached."""
    return host not in (frame.get("allowed_hosts") or [])


def hosts_of(task: Json) -> list[str]:
    """The hosts the task says its commands reach (`inputs.hosts`). This worker runs local
    commands and reaches nothing by itself; the task declares what its commands need, the
    worker holds that against the frame before the first command runs, and a refused host
    means the commands cannot run."""
    hosts = task.get("inputs", {}).get("hosts")
    if isinstance(hosts, list) and all(isinstance(h, str) for h in hosts):
        return list(dict.fromkeys(hosts))
    return []


@dataclass
class Produced:
    artifact_id: str
    kind: str
    media_type: str
    content: bytes

    @property
    def digest(self) -> str:
        return sha256(self.content)

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
    plan: list[PlannedStep]
    start_index: int
    inherited: list[Produced]  # produced before the checkpoint this assignment resumes from
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
        if self.outcome is not None:
            state["outcome"] = self.outcome
        if self.checkpoint_ref is not None:
            state["checkpoint_ref"] = self.checkpoint_ref
        if self.reason is not None:
            state["reason"] = self.reason
        if self.started_at is not None:
            state["started_at"] = self.started_at
        if self.finished_at is not None:
            state["finished_at"] = self.finished_at
        return state


class Worker:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.fault: str | None = options.fault
        self.profile: str = options.profile
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
            "capabilities": [TOOL, "shell.sandboxed", "workspace.isolated"],
            "consumption": {"kinds": kinds, "resource_classes": [self.resource_class]},
            "supports": {
                "native_pause": False,
                "step_boundary_signal": True,
                "streaming_events": True,
                "estimate": True,
            },
            "max_concurrent_assignments": MAX_CONCURRENT,
        }

    def estimate(self, request: Json) -> Json:
        plan = plan_for(request.get("task", {}), self.profile, self.options)
        start = self._resume_index(request.get("context", {}).get("checkpoint_ref"), plan)
        remaining = plan[start:]
        seconds = round(sum(s.seconds for s in remaining), 3)
        return {
            "confidence": "low",
            "compute_seconds": seconds,
            "resource_class": self.resource_class,
            "wall_seconds": int(seconds) + 1,
            "steps": len(remaining),
        }

    # -- checkpoints --

    def _checkpoint_path(self, ref: str) -> Path:
        return self.state_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", ref) + ".json")

    def _write_checkpoint(self, assignment: Assignment, index: int, step: PlannedStep) -> str:
        ref = f"ckpt/{assignment.id}/{step.step_id}"
        produced = assignment.inherited + assignment.produced
        record = {
            "assignment_id": assignment.id,
            "index": index,
            "plan": [s.step_id for s in assignment.plan],
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
        self._checkpoint_path(ref).write_text(json.dumps(record), encoding="utf-8")
        return ref

    def _load_checkpoint(self, ref: str) -> Json | None:
        path = self._checkpoint_path(ref)
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
        plan = plan_for(body["task"], self.profile, self.options)
        with self.lock:
            if assignment_id in self.assignments:
                return 409, {"title": "assignment exists", "status": 409}
            running = sum(1 for a in self.assignments.values() if a.status != "finished")
            if running >= MAX_CONCURRENT:
                return 503, {"title": "at capacity", "status": 503}
            ref = body.get("context", {}).get("checkpoint_ref")
            inherited: list[Produced] = []
            start = 0
            rejection: str | None = None
            if ref:
                record = self._load_checkpoint(ref)
                if record is None:
                    rejection = f"unknown checkpoint {ref}"
                elif record.get("plan") != [s.step_id for s in plan]:
                    rejection = f"checkpoint {ref} belongs to a different plan"
                else:
                    start = int(record["index"]) + 1
                    inherited = [
                        Produced(
                            p["artifact_id"],
                            p["kind"],
                            p["media_type"],
                            base64.b64decode(p["content"]),
                        )
                        for p in record["produced"]
                    ]
            assignment = Assignment(body, plan, start, inherited)
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

    def _run(self, assignment: Assignment) -> None:
        frame = assignment.body["frame"]
        credential = self._first_credential(assignment.body)
        deferred: list[Json] = []
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
            with assignment.lock:
                self._emit(
                    assignment,
                    {
                        "type": "step.started",
                        "step_id": step.step_id,
                        "kind": step.kind,
                        "summary": step.summary,
                    },
                )
            refused = outside_frame(TOOL, frame) and self.fault != "W-07"
            refused_host: str | None = None
            if index == assignment.start_index:
                # The hosts the task reaches are held against the frame once, before the first
                # command runs: reached, or refused visibly, never reached in silence.
                for host in hosts_of(assignment.body["task"]):
                    reach: Json = {
                        "type": "tool.called",
                        "step_id": step.step_id,
                        "tool": TOOL,
                        "host": host,
                        "arguments_digest": sha256(host.encode()),
                    }
                    if refused:
                        reach["refused"] = True
                        reach["reason"] = f"{TOOL} is outside the frame's allowed_tools"
                    elif host_outside_frame(host, frame) and self.fault != "W-13":
                        reach["refused"] = True
                        reach["reason"] = f"{host} is not in the frame's allowed_hosts"
                        refused_host = refused_host or host
                    with assignment.lock:
                        self._emit(assignment, reach)
            digest = step.command if self.fault == "W-09" else sha256(step.command.encode())
            call: Json = {
                "type": "tool.called",
                "step_id": step.step_id,
                "tool": TOOL,
                "arguments_digest": digest,
            }
            if refused:
                call["refused"] = True
                call["reason"] = f"{TOOL} is outside the frame's allowed_tools"
            with assignment.lock:
                self._emit(assignment, call)
            output = b""
            failure: str | None = None
            if refused:
                failure = f"step {step.step_id!r} needs {TOOL}, which the frame does not allow"
            elif refused_host is not None:
                refused = True
                failure = (
                    f"step {step.step_id!r} needs host {refused_host!r}, which the frame does "
                    "not allow"
                )
            else:
                output, failure = run_command(step.command)
                if self.fault == "W-08-log" and credential:
                    log(f"credential {credential[0]}={credential[1]}")  # the W-08-log fault
            if step.progress and not refused:
                progress: Json = {
                    "type": "step.progress",
                    "step_id": step.step_id,
                    "message": output.decode(errors="replace").strip() or step.summary,
                    "progress": {
                        "current": step.progress[0],
                        "total": step.progress[1],
                        "unit": "epochs",
                    },
                }
                with assignment.lock:
                    self._emit(assignment, progress)
            if self.fault == "W-08-event" and credential:
                with assignment.lock:
                    self._emit(
                        assignment,
                        {
                            "type": "step.progress",
                            "step_id": step.step_id,
                            "message": f"using {credential[0]}={credential[1]}",  # the W-08 fault
                        },
                    )
            remaining = step.seconds - (time.monotonic() - began)
            if remaining > 0 and not refused:
                time.sleep(remaining)
            if not refused:
                self._produce(assignment, step, output, credential)
            consumption: Json = {
                "type": "consumption.reported",
                "step_id": step.step_id,
                "compute_seconds": round(max(time.monotonic() - began, 0.001), 3),
                "resource_class": self.resource_class,
            }
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
        with assignment.lock:
            for consumption in deferred:
                self._emit(assignment, consumption)
            self._finish(
                assignment,
                "succeeded",
                summary=f"{len(assignment.plan) - assignment.start_index} step(s) completed",
            )

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
        output: bytes,
        credential: tuple[str, str] | None,
    ) -> None:
        for spec in step.artifacts:
            content = spec.content if spec.content is not None else output
            if self.fault == "W-08-artifact" and credential:
                content += f"\n{credential[0]}={credential[1]}\n".encode()  # the W-08 fault
            produced = Produced(spec.artifact_id, spec.kind, spec.media_type, content)
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
    ) -> None:
        """Caller holds the assignment's lock."""
        event: Json = {"type": "assignment.finished", "outcome": outcome}
        if reason is not None:
            event["reason"] = reason
        if checkpoint_ref is not None:
            event["checkpoint_ref"] = checkpoint_ref
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


def run_command(command: str) -> tuple[bytes, str | None]:
    """Run one shell command. This worker exists to run commands; that is its capability."""
    try:
        completed = subprocess.run(  # noqa: S602 — a shell wrapper runs shell commands by design
            command,
            shell=True,
            capture_output=True,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return b"", f"command exceeded {COMMAND_TIMEOUT}s"
    if completed.returncode != 0:
        return completed.stdout, f"command exited with {completed.returncode}"
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

    # -- helpers --

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

    # -- routes --

    def do_GET(self) -> None:
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        if parts == ["v1", "capabilities"]:
            self._json(200, self.worker.capabilities())
        elif parts == ["v1", "health"]:
            running = sum(1 for a in self.worker.assignments.values() if a.status != "finished")
            if running < MAX_CONCURRENT:
                self._json(200, {"status": "ready"})
            else:
                self._json(503, {"status": "not_ready", "detail": "at capacity"})
        elif len(parts) == 3 and parts[:2] == ["v1", "assignments"]:
            if (assignment := self._assignment(parts[2])) is not None:
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
    # The launch convention of the execution port: an execution adapter that starts this
    # worker tells it where to listen and where its state lives through these two variables.
    # The options override them; without either, the defaults below apply.
    port = int(os.environ.get("TAKTUS_UNIT_PORT") or 9000)
    state_dir = os.environ.get("TAKTUS_UNIT_STATE_DIR") or None
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument("--profile", choices=["quick", "longrun"], default="quick")
    parser.add_argument("--fault", choices=sorted(FAULTS), help="violate exactly one check")
    parser.add_argument("--list-faults", action="store_true", help="print the faults and exit")
    parser.add_argument("--state-dir", default=state_dir, help="where checkpoints are written")
    parser.add_argument("--resource-class", default="cpu.small", help="the class reported")
    parser.add_argument("--step-seconds", type=float, default=0.3, help="quick: seconds per step")
    parser.add_argument("--epochs", type=int, default=4, help="longrun: number of epochs")
    parser.add_argument(
        "--epoch-seconds", type=float, default=0.5, help="longrun: seconds per epoch"
    )
    args = parser.parse_args(argv)
    if args.state_dir is None:
        args.state_dir = str(Path.home() / ".cache" / "taktus-script-worker" / secrets.token_hex(4))
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
    log(f"listening on http://{args.host}:{server.server_port} profile {args.profile}{fault}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
