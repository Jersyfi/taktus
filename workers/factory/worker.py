#!/usr/bin/env python3
"""The `factory` worker: a whole software factory behind the worker contract v1 (ADR-0157).

A software factory is a service that takes a task — implement this change — and returns the
finished change, after its own agents, its own review and its own checks. This worker hands a
step's task to one, observes it, and returns its change. It offers one capability,
`change.implement`. It names no product: it is generic over a factory's task API in three
calls — submit a task, read its state, fetch its change — and a *profile* maps those calls onto
one factory's API (`--profile`, *Profiles* in the README). The shipped profile is `generic`.

    python3 workers/factory/worker.py --port 9020 --factory https://factory.example \
        --stores eu

`--stores` is required: where the factory keeps what it is sent, `own`, `eu` or `elsewhere`.
The worker declares it as `data_location`, and a tenant whose residency rule does not admit it
is never handed to this worker (principle 11). Nothing is assumed.

An assignment is a step per call: `submit`, then one step per stage the factory reports, then
`fetch`, with the task's commands before and after the work around them. Each step reports the
difference in the factory's running cost, ends with a boundary and a checkpoint that names the
factory's task. A stop lands on the next boundary and cancels nothing at the factory; a resumed
assignment observes the same task and submits nothing a second time. Steering, handover and the
outbound binding are not offered.

The factory's credential arrives in this process's environment under the name the assignment
references (`FACTORY_TOKEN`, or `--credential NAME`), put there by whoever started the worker.
It goes to the factory in the profile's header and nowhere else: never into an event, an
artifact, a state or a log — except under the three W-08 faults, which exist to be caught.

`--fault NAME` makes the worker violate exactly one conformance check; `--list-faults` prints
them. This file imports nothing from src/taktus and needs nothing but Python's standard library.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
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
VERSION = "0.1.0"  # this worker's own version, recorded in the provenance of what it produces
TOOL = "change.implement"
CAPABILITIES = [TOOL]
"""What this worker offers; the release's list of what it ships reads it (ADR-0118)."""
LOCATIONS = ("own", "eu", "elsewhere")
MAX_CONCURRENT = 4
COMMAND_TIMEOUT = 60
REQUEST_TIMEOUT = 30.0
DEFAULT_CREDENTIAL = "FACTORY_TOKEN"

GENERIC: Json = {
    "name": "generic",
    "submit": {
        "method": "POST",
        "path": "/tasks",
        "body": {
            "title": "$goal",
            "description": "$brief",
            "acceptance": "$acceptance",
            "reference": "$assignment",
            "inputs": "$inputs",
        },
        "id": "id",
    },
    "state": {
        "path": "/tasks/{id}",
        "state": "state",
        "stages": "stages",
        "stage_summary": "summary",
        "cost": "cost.amount",
        "summary": "summary",
        "reason": "reason",
    },
    "states": {"succeeded": ["succeeded"], "failed": ["failed", "cancelled"]},
    "change": {"path": "/tasks/{id}/change"},
    "auth": {"header": "Authorization", "prefix": "Bearer "},
}
"""The generic task API (README, *Profiles*). A profile for a product is a file of the same
shape, written by its operator; none is shipped (ADR-0157 §3)."""

FAULTS: dict[str, str] = {
    "W-01": "capabilities declares no consumption kind",
    "W-02": "estimate answers 501 instead of an estimate",
    "W-02-estimator": "the declared estimator yields a tenth of the estimate",
    "W-03-gap": "the second event is skipped: seq jumps from 1 to 3",
    "W-03-resume": "Last-Event-ID and ?after= are ignored; the stream always replays from 1",
    "W-04": "consumption is reported for every step at the end, just before assignment.finished",
    "W-05": "no step.boundary is ever emitted, although checkpoints are still written",
    "W-06": "a stop skips the boundary of the running step and reports the previous checkpoint",
    "W-07": "a call to the factory outside the frame's tools is made without refused: true",
    "W-08-event": "the value of the credential is written into a step.progress message",
    "W-08-artifact": "the value of the credential is written into an artifact",
    "W-08-log": "the value of the credential is written to the worker's log",
    "W-09": "tool.called carries the request in clear instead of its sha256",
    "W-10": "an estimate above the limits is accepted; the assignment fails after its first step",
    "W-11": "a resumed assignment produces the artifacts from before its checkpoint again",
    "W-13": "the factory's host outside allowed_hosts is reached without refused: true",
    "W-14": "the limits are ignored once running: steps keep starting after the total crossed them",
    "W-15": "an assignment beyond max_concurrent_assignments is accepted instead of answered 503",
    "W-16": "the state of an id never received is answered 200, accepted, instead of 404",
    "W-17": "an assignment whose id is held is accepted again as a second one instead of 409",
    "W-18": "the task's commands before and after the work are ignored",
}


def check_of(fault: str) -> str:
    return fault[:4]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(message: str) -> None:
    sys.stderr.write(f"{now()} factory-worker {message}\n")
    sys.stderr.flush()


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def pick(document: Any, path: str | None) -> Any:
    """The value at a dotted path of a JSON document, or None."""
    if not path:
        return None
    for part in path.split("."):
        if not isinstance(document, dict):
            return None
        document = document.get(part)
    return document


# --- the factory --------------------------------------------------------------------------------


class FactoryError(Exception):
    """The factory could not be used: unreachable, an answer that is not what the profile says.
    The message never carries the credential."""


class Factory:
    """The factory's task API through one profile."""

    def __init__(self, base: str, profile: Json) -> None:
        url = urlparse(base)
        if url.scheme not in ("http", "https") or not url.hostname:
            raise ValueError(f"--factory takes an http or https address, not {base!r}")
        self.secure = url.scheme == "https"
        self.port = url.port or (443 if self.secure else 80)
        self.hostname = url.hostname
        self.host = url.hostname if url.port is None else f"{url.hostname}:{url.port}"
        """The host the frame must allow, as the contract writes a host."""
        self.prefix = url.path.rstrip("/")
        self.profile = profile

    def _call(self, method: str, path: str, token: str | None, body: Json | None = None) -> Json:
        headers = {"Accept": "application/json"}
        auth = self.profile.get("auth") or {}
        if token is not None and auth.get("header"):
            headers[str(auth["header"])] = str(auth.get("prefix", "")) + token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection: http.client.HTTPConnection
        if self.secure:
            connection = http.client.HTTPSConnection(
                self.hostname, self.port, timeout=REQUEST_TIMEOUT
            )
        else:
            connection = http.client.HTTPConnection(
                self.hostname, self.port, timeout=REQUEST_TIMEOUT
            )
        try:
            connection.request(method, self.prefix + path, body=data, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as error:
            raise FactoryError(
                f"the factory did not answer {method} {path}: {type(error).__name__}"
            ) from None
        finally:
            connection.close()
        if response.status >= 400:
            raise FactoryError(f"the factory answered {method} {path} with {response.status}")
        try:
            answer = json.loads(raw or b"{}")
        except ValueError as error:
            raise FactoryError(f"the factory's answer to {method} {path} is not JSON") from error
        if not isinstance(answer, dict):
            raise FactoryError(f"the factory's answer to {method} {path} is not an object")
        return answer

    def submit(self, task: Json, assignment_id: str, token: str | None) -> str:
        spec = self.profile["submit"]
        body = render(spec.get("body") or {}, task, assignment_id)
        answer = self._call(str(spec.get("method", "POST")), str(spec["path"]), token, body)
        task_id = pick(answer, spec.get("id", "id"))
        if not isinstance(task_id, str) or not task_id:
            raise FactoryError("the factory's answer to the task names no id")
        return task_id

    def state(self, task_id: str, token: str | None) -> Json:
        """The task's state as the worker reads it: `state` one of running, succeeded or
        failed; `stages` the summaries of the stages done; `cost` the running cost."""
        spec = self.profile["state"]
        answer = self._call("GET", str(spec["path"]).format(id=task_id), token)
        states = self.profile.get("states") or {}
        word = pick(answer, spec.get("state"))
        if word in (states.get("succeeded") or []):
            state = "succeeded"
        elif word in (states.get("failed") or []):
            state = "failed"
        else:
            state = "running"
        stages = pick(answer, spec.get("stages")) or []
        summaries = []
        for stage in stages if isinstance(stages, list) else []:
            text = pick(stage, spec.get("stage_summary")) if isinstance(stage, dict) else stage
            summaries.append(str(text or "a stage of the factory").strip()[:200] or "a stage")
        try:
            cost = float(pick(answer, spec.get("cost")) or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        return {
            "state": state,
            "stages": summaries,
            "cost": cost,
            "summary": pick(answer, spec.get("summary")),
            "reason": pick(answer, spec.get("reason")),
        }

    def change(self, task_id: str, token: str | None) -> Json:
        spec = self.profile["change"]
        answer = self._call("GET", str(spec["path"]).format(id=task_id), token)
        change = pick(answer, spec.get("document")) if spec.get("document") else answer
        if not isinstance(change, dict) or not isinstance(change.get("files", []), list):
            raise FactoryError("the factory's change is not a changeset")
        return {
            "base": change.get("base"),
            "files": list(change.get("files") or []),
            "deleted": list(change.get("deleted") or []),
        }


def render(template: Any, task: Json, assignment_id: str) -> Any:
    """The profile's body with the task's values in place of `$goal`, `$brief`, `$acceptance`,
    `$assignment` and `$inputs`."""
    acceptance = [str(a) for a in task.get("acceptance") or []]
    brief = str(task.get("goal", ""))
    if acceptance:
        brief += "\n\nAccepted when:\n" + "\n".join(f"- {a}" for a in acceptance)
    values = {
        "$goal": str(task.get("goal", "")),
        "$brief": brief,
        "$acceptance": acceptance,
        "$assignment": assignment_id,
        "$inputs": task.get("inputs") or {},
    }
    if isinstance(template, str):
        return values.get(template, template)
    if isinstance(template, dict):
        return {k: render(v, task, assignment_id) for k, v in template.items()}
    if isinstance(template, list):
        return [render(v, task, assignment_id) for v in template]
    return template


def load_profile(path: str | None) -> Json:
    if path is None or path == "generic":
        return json.loads(json.dumps(GENERIC))
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    for part in ("submit", "state", "change"):
        if not isinstance(profile.get(part), dict) or "path" not in profile[part]:
            raise ValueError(f"the profile {path} names no path for {part!r}")
    return dict(profile)


# --- state ------------------------------------------------------------------------------------


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
class Progress:
    """Where an assignment is: what a checkpoint keeps and a resume continues from."""

    before: bool = False
    task: str | None = None
    seen: int = 0
    cost: float = 0.0
    ended: str | None = None  # the factory's end: succeeded or failed
    fetched: bool = False
    after: bool = False
    steps: int = 0
    summary: str | None = None  # the factory's own summary of the change

    def to_json(self) -> Json:
        return dict(self.__dict__)

    @classmethod
    def from_json(cls, data: Json) -> Progress:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Next:
    step_id: str
    kind: str
    summary: str
    calls: bool  # whether the step calls the factory, under the frame


@dataclass
class Assignment:
    body: Json
    progress: Progress
    inherited: list[Produced]
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

    @property
    def task(self) -> Json:
        return dict(self.body["task"])

    def state(self) -> Json:
        state: Json = {
            "assignment_id": self.id,
            "status": self.status,
            "last_seq": self.seq,
            "accepted_at": self.accepted_at,
        }
        for name in ("outcome", "checkpoint_ref", "reason", "started_at", "finished_at"):
            value = getattr(self, name)
            if value is not None:
                state[name] = value
        return state


class Worker:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.fault: str | None = options.fault
        self.factory = Factory(options.factory, load_profile(options.profile))
        self.currency: str = options.currency
        self.state_dir = Path(options.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.assignments: dict[str, Assignment] = {}
        self.lock = threading.Lock()

    # -- declarations --

    def capabilities(self) -> Json:
        kinds = [] if self.fault == "W-01" else ["currency"]
        estimate = self._whole()
        if self.fault == "W-02-estimator":
            estimate = {
                **estimate,
                "currency": {self.currency: estimate["currency"][self.currency] / 10},
            }
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "data_location": self.options.stores,
            "capabilities": list(CAPABILITIES),
            "consumption": {"kinds": kinds, "currencies": [self.currency]},
            "supports": {
                "native_pause": False,
                "steering": False,
                "handover": False,
                "step_boundary_signal": True,
                "streaming_events": True,
                "estimate": True,
            },
            "max_concurrent_assignments": self.options.max_concurrent,
            "estimator": {"kind": "fixed", "estimate": estimate},
        }

    def _steps_of(self, task: Json) -> int:
        """Every step a fresh assignment of the task takes, as far as it can be known."""
        around = int(isinstance(task.get("before"), dict)) + int(
            isinstance(task.get("after"), dict)
        )
        return 2 + self.options.estimate_stages + around

    def _whole(self) -> Json:
        """The estimate of a fresh assignment with a command before and after the work: what
        the declared estimator yields, never less than `estimate` answers (W-02)."""
        return {
            "confidence": "low",
            "currency": {self.currency: round(self.options.estimate_amount, 6)},
            "wall_seconds": int(self.options.estimate_seconds) + 1,
            "steps": 2 + self.options.estimate_stages + 2,
        }

    def expected(self, following: Next) -> float:
        """A step's own expected cost: the estimate shared among the stages it expects. A
        call that submits or fetches costs nothing of its own."""
        if following.kind != "stage":
            return 0.0
        return self.options.estimate_amount / max(self.options.estimate_stages, 1)

    def estimate(self, request: Json) -> Json:
        task = request.get("task") or {}
        progress = Progress()
        ref = (request.get("context") or {}).get("checkpoint_ref")
        if ref:
            record = self._load_checkpoint(str(ref))
            if record is not None:
                progress = Progress.from_json(record["progress"])
        stages_left = max(self.options.estimate_stages - progress.seen, 0)
        if progress.ended:
            stages_left = 0
        fraction = stages_left / max(self.options.estimate_stages, 1)
        steps = self._steps_of(task) - progress.steps
        return {
            "confidence": "low",
            "currency": {self.currency: round(self.options.estimate_amount * fraction, 6)},
            "wall_seconds": int(self.options.estimate_seconds * fraction) + 1,
            "steps": max(steps, 0),
        }

    # -- checkpoints --

    def _checkpoint_path(self, ref: str) -> Path:
        return self.state_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", ref) + ".json")

    def _write_checkpoint(self, assignment: Assignment, step_id: str) -> str:
        ref = f"ckpt/{assignment.id}/{step_id}"
        record = {
            "assignment_id": assignment.id,
            "progress": assignment.progress.to_json(),
            "produced": [
                {
                    "artifact_id": p.artifact_id,
                    "kind": p.kind,
                    "media_type": p.media_type,
                    "content": base64.b64encode(p.content).decode(),
                }
                for p in assignment.inherited + assignment.produced
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

    # -- assignments --

    def accept(self, body: Any) -> tuple[int, Json]:
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
            progress, inherited, rejection = Progress(), [], None
            ref = (body.get("context") or {}).get("checkpoint_ref")
            if ref:
                record = self._load_checkpoint(str(ref))
                if record is None:
                    rejection = f"unknown checkpoint {ref}"
                else:
                    progress = Progress.from_json(record["progress"])
                    inherited = [
                        Produced(
                            p["artifact_id"],
                            p["kind"],
                            p["media_type"],
                            base64.b64decode(p["content"]),
                        )
                        for p in record["produced"]
                    ]
            assignment = Assignment(body, progress, inherited)
            if rejection is None:
                rejection = self._does_not_fit(body)
            self.assignments[assignment_id] = assignment
            if rejection is not None:
                self._reject(assignment, rejection)
                return 201, assignment.state()
        threading.Thread(target=self._run, args=(assignment,), daemon=True).start()
        return 201, assignment.state()

    def _does_not_fit(self, body: Json) -> str | None:
        names = [c.get("name") for c in body.get("credentials", []) if isinstance(c, dict)]
        if self.options.credential not in names:
            return (
                f"the assignment references no credential {self.options.credential}, which the "
                "factory needs"
            )
        estimate = self.estimate(body)
        if self.fault != "W-10":
            currency = (body["limits"].get("currency") or {}).get(self.currency)
            if currency is None:
                return f"this worker costs {self.currency}, and the limits carry no limit in it"
            if estimate["currency"][self.currency] > float(currency):
                return (
                    f"estimated {estimate['currency'][self.currency]:g} {self.currency} exceeds "
                    f"the limit of {float(currency):g} {self.currency}"
                )
        frame = body["frame"]
        if estimate["steps"] > frame["max_steps"]:
            return f"{estimate['steps']} steps needed, frame allows {frame['max_steps']}"
        deadline = frame.get("deadline")
        if deadline:
            try:
                until = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
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

    def stop(self, assignment: Assignment) -> Json:
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

    def _next(self, assignment: Assignment) -> Next | None:
        progress, task = assignment.progress, assignment.task
        if isinstance(task.get("before"), dict) and not progress.before and self.fault != "W-18":
            return Next("before", "shell", "the command before the work", False)
        if progress.task is None:
            return Next("submit", "submit", "hand the task to the factory", True)
        if progress.ended is None:
            return Next(
                f"stage-{progress.seen + 1}", "stage", "wait for the factory's next stage", True
            )
        if not progress.fetched:
            return Next("fetch", "fetch", "fetch the factory's change", True)
        if isinstance(task.get("after"), dict) and not progress.after and self.fault != "W-18":
            return Next("after", "shell", "the command after the work", False)
        return None

    def _run(self, assignment: Assignment) -> None:
        frame = assignment.body["frame"]
        token = os.environ.get(self.options.credential)
        log(f"credential {self.options.credential}: {'present' if token else 'absent'}")
        deferred: list[Json] = []
        used = 0.0  # what this assignment has cost so far: its running total
        last_checkpoint: str | None = (assignment.body.get("context") or {}).get("checkpoint_ref")
        workspace = self.state_dir / "workspaces" / assignment.id
        workspace.mkdir(parents=True, exist_ok=True)
        with assignment.lock:
            assignment.status = "running"
            assignment.started_at = now()
            if self.fault == "W-11":
                for produced in assignment.inherited:
                    assignment.produced.append(produced)
                    self._emit(assignment, artifact_event(assignment, produced, None))
        while (step := self._next(assignment)) is not None:
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
            failure: str | None = None
            cost = 0.0
            if step.calls:
                failure = self._held(assignment, step, frame)
            if failure is None:
                try:
                    cost, failure = self._do(assignment, step, token, workspace)
                except FactoryError as error:
                    failure = f"step {step.step_id!r}: {error}"
            if self.fault == "W-08-log" and token:
                log(f"credential {self.options.credential}={token}")  # the W-08-log fault
            if self.fault == "W-08-event" and token:
                with assignment.lock:
                    self._emit(
                        assignment,
                        {
                            "type": "step.progress",
                            "step_id": step.step_id,
                            "message": f"using {self.options.credential}={token}",  # the fault
                        },
                    )
            assignment.progress.steps += 1
            consumption: Json = {
                "type": "consumption.reported",
                "step_id": step.step_id,
                "currency": {self.currency: round(max(cost, 0.0), 6)},
            }
            used += max(cost, 0.0)
            with assignment.lock:
                if self.fault == "W-04":
                    deferred.append(consumption)
                else:
                    self._emit(assignment, consumption)
                skip_boundary = self.fault == "W-06" and assignment.stop_requested
                checkpoint = self._write_checkpoint(assignment, step.step_id)
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
                if self.fault == "W-10" and assignment.progress.steps == 1:
                    limit = (assignment.body["limits"].get("currency") or {}).get(self.currency)
                    if limit is not None and self._whole()["currency"][self.currency] > float(
                        limit
                    ):
                        self._finish(assignment, "failed", reason="limits exceeded after starting")
                        return
                if assignment.stop_requested:
                    self._finish(assignment, "stopped", checkpoint_ref=last_checkpoint)
                    return
                following = self._next(assignment)
                if following is not None and self.fault != "W-14":
                    halt = self._over_ceiling(assignment.body, used, following)
                    if halt is not None:
                        self._finish(
                            assignment,
                            "stopped",
                            reason=halt,
                            checkpoint_ref=last_checkpoint,
                            limit="currency",
                        )
                        return
            remaining = 0.01 - (time.monotonic() - began)
            if remaining > 0:
                time.sleep(remaining)
        with assignment.lock:
            for consumption in deferred:
                self._emit(assignment, consumption)
            self._finish(assignment, "succeeded", summary="the factory's change is fetched")

    def _held(self, assignment: Assignment, step: Next, frame: Json) -> str | None:
        """The step's call to the factory, held against the frame: reported as `tool.called`
        with the factory's host, refused visibly where the frame does not allow the capability
        or the host (W-07, W-13). The reason, or None when the call may be made."""
        request = f"{step.kind} {self.factory.host} {assignment.progress.task or ''}"
        call: Json = {
            "type": "tool.called",
            "step_id": step.step_id,
            "tool": TOOL,
            "host": self.factory.host,
            "arguments_digest": request if self.fault == "W-09" else sha256(request.encode()),
        }
        reason = None
        if TOOL not in frame.get("allowed_tools", []) and self.fault != "W-07":
            reason = f"{TOOL} is outside the frame's allowed_tools"
        elif self.factory.host not in (frame.get("allowed_hosts") or []) and self.fault != "W-13":
            reason = f"{self.factory.host} is not in the frame's allowed_hosts"
        if reason is not None:
            call["refused"] = True
            call["reason"] = reason
        with assignment.lock:
            self._emit(assignment, call)
        return None if reason is None else f"step {step.step_id!r}: {reason}; nothing was sent"

    def _do(
        self, assignment: Assignment, step: Next, token: str | None, workspace: Path
    ) -> tuple[float, str | None]:
        """Carry out one step: what it cost, and why it failed, if it did."""
        progress, task = assignment.progress, assignment.task
        if step.step_id in ("before", "after"):
            spec = task[step.step_id]
            argv = tuple(str(part) for part in spec.get("command") or ())
            before = step.step_id == "before"
            output, failure = run_program(argv, workspace, before=before)
            if before:
                progress.before = True
            else:
                progress.after = True
            if failure is None or before:
                self._produce(
                    assignment, step, str(spec.get("artifact")), "output", "text/plain", output
                )
            return 0.0, failure
        if step.kind == "submit":
            progress.task = self.factory.submit(task, assignment.id, token)
            record = {
                "factory_task": progress.task,
                "factory": self.factory.host,
                "profile": self.factory.profile.get("name", "unnamed"),
                "stores": self.options.stores,
            }
            self._produce(
                assignment,
                step,
                "submission",
                "factory.submission",
                "application/json",
                json.dumps(record).encode(),
            )
            return 0.0, None
        if progress.task is None:
            raise FactoryError("the factory's task is not known")
        if step.kind == "stage":
            while True:
                state = self.factory.state(progress.task, token)
                if len(state["stages"]) > progress.seen:
                    summary = state["stages"][progress.seen]
                    progress.seen += 1
                    if state["state"] != "running" and len(state["stages"]) == progress.seen:
                        progress.ended = state["state"]
                    break
                if state["state"] != "running":
                    progress.ended = state["state"]
                    summary = f"the factory's task {state['state']}"
                    break
                time.sleep(self.options.poll_seconds)
            with assignment.lock:
                self._emit(
                    assignment,
                    {"type": "step.progress", "step_id": step.step_id, "message": summary},
                )
            cost = state["cost"] - progress.cost
            progress.cost = state["cost"]
            if progress.ended == "failed":
                reason = state.get("reason") or "no reason given"
                return cost, f"the factory's task failed: {str(reason)[:300]}"
            if state.get("summary"):
                progress.summary = str(state["summary"])[:4000]
            return cost, None
        # fetch
        change = self.factory.change(progress.task, token)
        write_change(workspace, change)
        progress.fetched = True
        summary = progress.summary or "The factory implemented the change."
        self._produce(assignment, step, "summary", "report", "text/plain", str(summary).encode())
        document: Json = {
            "base": change["base"],
            "files": change["files"],
            "deleted": change["deleted"],
        }
        self._produce(
            assignment,
            step,
            "changeset",
            "changeset",
            "application/json",
            json.dumps(document, ensure_ascii=False).encode(),
        )
        return 0.0, None

    def _produce(
        self,
        assignment: Assignment,
        step: Next,
        artifact_id: str,
        kind: str,
        media_type: str,
        content: bytes,
    ) -> None:
        if any(p.artifact_id == artifact_id for p in assignment.inherited):
            return  # produced before the checkpoint this assignment resumes from (W-11)
        token = os.environ.get(self.options.credential)
        if self.fault == "W-08-artifact" and token and step.step_id not in ("before", "after"):
            content += f"\n{self.options.credential}={token}\n".encode()  # the W-08 fault
        produced = Produced(artifact_id, kind, media_type, content)
        with assignment.lock:
            assignment.produced.append(produced)
            self._emit(assignment, artifact_event(assignment, produced, step.step_id))

    def _over_ceiling(self, body: Json, used: float, following: Next) -> str | None:
        """The limits are this worker's hard ceiling (W-14): the next step does not start when
        the running total and that step's expected cost would exceed the currency limit."""
        limit = (body["limits"].get("currency") or {}).get(self.currency)
        if limit is None:
            return None
        ceiling = float(limit)
        expected = self.expected(following)
        if used >= ceiling or used + expected > ceiling:
            return (
                f"the running total of {used:g} {self.currency} and the {expected:g} the step "
                f"{following.step_id!r} expects would exceed the limit of {ceiling:g}; halted at "
                "the boundary"
            )
        return None

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


def artifact_event(assignment: Assignment, produced: Produced, step_id: str | None) -> Json:
    event: Json = {"type": "artifact.produced", **produced.describe(assignment.id)}
    event["artifact_id"] = event.pop("id")
    if step_id is not None:
        event["step_id"] = step_id
    return event


def write_change(workspace: Path, change: Json) -> None:
    """The factory's change, written into the workspace, so that the command after the work
    runs on it. A path that leads out of the workspace is not written."""
    root = workspace.resolve()
    for entry in change["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        target = (root / entry["path"]).resolve()
        if root not in target.parents:
            continue
        content = entry.get("content", "")
        raw = (
            base64.b64decode(content)
            if entry.get("encoding") == "base64"
            else str(content).encode("utf-8")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for path in change["deleted"]:
        target = (root / str(path)).resolve()
        if root in target.parents and target.is_file():
            target.unlink()


def run_program(
    argv: tuple[str, ...], workspace: Path, *, before: bool
) -> tuple[bytes, str | None]:
    """The task's command before or after the work: a program and its arguments, run without a
    shell, in the workspace, with no credential in its environment (contracts/worker/v1 §3)."""
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
    environment = {k: os.environ[k] for k in keep if k in os.environ}
    which = "before" if before else "after"
    try:
        completed = subprocess.run(  # noqa: S603 — the task's own command, by design
            list(argv),
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if before else subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=COMMAND_TIMEOUT,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return b"", f"the command {which} the work exceeded {COMMAND_TIMEOUT}s"
    except OSError as error:
        return b"", f"the command {which} the work could not be started: {error.strerror}"
    if completed.returncode != 0:
        return completed.stdout, f"the command {which} the work exited with {completed.returncode}"
    return completed.stdout, None


def validate_assignment(body: Any) -> str | None:
    """The shape this worker needs; full validation is the conformance suite's job."""
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
    if (body.get("callback") or {}).get("events") != "sse":
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
                self._json(202, self.worker.stop(assignment))
        elif (
            len(parts) == 4
            and parts[:2] == ["v1", "assignments"]
            and parts[3]
            in (
                "messages",
                "handover",
            )
        ):
            if self._assignment(parts[2]) is not None:
                self._problem(
                    400,
                    f"{parts[3]} not offered",
                    "this worker declares neither steering nor handover (ADR-0157)",
                )
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
    # The launch convention of the execution port: an execution adapter that starts this worker
    # tells it where to listen and where its state lives through these two variables; the
    # factory, its profile and where it stores through the unit's environment (ADR-0090).
    port = int(os.environ.get("TAKTUS_UNIT_PORT") or 9020)
    state_dir = os.environ.get("TAKTUS_UNIT_STATE_DIR") or None
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument(
        "--factory",
        default=os.environ.get("FACTORY_URL"),
        help="the base URL of the factory's task API (FACTORY_URL)",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("FACTORY_PROFILE") or "generic",
        help="a profile file mapping the factory's API, or generic (FACTORY_PROFILE)",
    )
    parser.add_argument(
        "--stores",
        choices=LOCATIONS,
        default=os.environ.get("FACTORY_STORES") or None,
        help="where the factory keeps what it is sent: own, eu or elsewhere (FACTORY_STORES); "
        "required, nothing is assumed",
    )
    parser.add_argument(
        "--credential",
        default=DEFAULT_CREDENTIAL,
        help="the name of the credential the factory is reached with",
    )
    parser.add_argument("--currency", default="eur", help="the currency the factory bills in")
    parser.add_argument(
        "--estimate-amount", type=float, default=2.0, help="the estimated cost of one task"
    )
    parser.add_argument(
        "--estimate-stages", type=int, default=3, help="the stages a task is expected to take"
    )
    parser.add_argument(
        "--estimate-seconds", type=float, default=1800.0, help="the expected wall time of a task"
    )
    parser.add_argument(
        "--poll-seconds", type=float, default=2.0, help="how often the factory's state is read"
    )
    parser.add_argument("--fault", choices=sorted(FAULTS), help="violate exactly one check")
    parser.add_argument("--list-faults", action="store_true", help="print the faults and exit")
    parser.add_argument("--state-dir", default=state_dir, help="where checkpoints are written")
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=MAX_CONCURRENT,
        help="assignments held at once; a further one is answered 503, at capacity",
    )
    args = parser.parse_args(argv)
    if args.list_faults:
        return args
    if not args.factory:
        parser.error("--factory is required: the base URL of the factory's task API")
    if args.stores is None:
        parser.error("--stores is required: own, eu or elsewhere; nothing is assumed")
    if args.currency != args.currency.lower() or not re.fullmatch(r"[a-z]{3}", args.currency):
        parser.error("--currency is an ISO 4217 code in lowercase")
    if args.estimate_amount <= 0 or args.estimate_stages < 1:
        parser.error("--estimate-amount must be above 0 and --estimate-stages at least 1")
    if args.max_concurrent < 1:
        parser.error("--max-concurrent must be at least 1")
    if args.state_dir is None:
        args.state_dir = str(
            Path.home() / ".cache" / "taktus-factory-worker" / secrets.token_hex(4)
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
    log(
        f"listening on http://{args.host}:{server.server_port}, factory "
        f"{Handler.worker.factory.host}, stores {args.stores}{fault}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
