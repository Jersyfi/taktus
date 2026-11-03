#!/usr/bin/env python3
"""The `a2a` worker: an agent of the open agent-to-agent protocol behind the worker contract v1.

The agent-to-agent protocol (A2A) lets one agent hand a task to another: a *message* is sent,
the agent answers with a *task* whose *status* changes as it works, and whose *artifacts* are
its results. This worker is the binding of the worker contract to that protocol (ADR-0172): it
speaks the contract to the control plane and A2A 0.3 over JSON-RPC to one agent. The agent
knows nothing of Taktus. The binding keeps every obligation the protocol does not carry — the
estimate, the limits, the stream with its boundaries, the stop, the commands before and after
the work.

    python3 workers/a2a/worker.py --port 9030 --agent https://agent.example \
        --capability report.draft --stores eu

`--capability` is required: what the agent does, named by function, never by the agent or its
product. `--stores` is required: where the agent keeps what it is sent, `own`, `eu` or
`elsewhere`. The worker declares both, and a tenant whose residency rule does not admit the
location is never handed to it (principle 11). Nothing is assumed.

An assignment is `send`, then one step per status change the agent reports (`turn-N`), then
`fetch`, with the task's commands before and after the work around them. Each step reports
the seconds it lasted as `compute_seconds`, the one quantity the binding measures, and ends with
a boundary and a checkpoint that names the agent's task. A stop lands on the next boundary and
cancels nothing at the agent; a resumed assignment observes the same task and sends nothing a
second time. A steering message is received at the next boundary and sent into the agent's
task. Handover and the outbound binding are not offered.

The agent's credential arrives in this process's environment under the name the assignment
references (`A2A_AGENT_TOKEN`, or `--credential NAME`), put there by whoever started the worker.
It goes to the agent in the header `--auth-header` names and nowhere else: never into an event,
an artifact, a state or a log — except under the three W-08 faults, which exist to be caught.

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
CAPABILITIES: list[str] = []
"""What this worker offers of its own: nothing. Its operator names the agent's capability
(`--capability`); the release's list of what it ships reads this (ADR-0118)."""
PROTOCOL = "0.3"
CARD_PATH = "/.well-known/agent-card.json"
LOCATIONS = ("own", "eu", "elsewhere")
CAPABILITY = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)+$")
MAX_CONCURRENT = 4
COMMAND_TIMEOUT = 60
REQUEST_TIMEOUT = 30.0
STOP_CEILING = 30.0
"""How long a turn may still wait for the agent once a stop was requested, unless the stop
names its own ceiling (contracts/worker/v1 §6)."""
DEFAULT_CREDENTIAL = "A2A_AGENT_TOKEN"
DEFAULT_RESOURCE_CLASS = "agent.remote"
ENDED = {"completed": "succeeded", "failed": "failed", "rejected": "failed", "canceled": "failed"}
"""The task states of the protocol that end a task, and what they end the assignment as."""
WAITING = ("input-required", "auth-required")
"""The task states in which the agent waits for a further message."""

FAULTS: dict[str, str] = {
    "W-01": "capabilities declares no consumption kind",
    "W-02": "estimate answers 501 instead of an estimate",
    "W-02-estimator": "the declared estimator yields a tenth of the estimate",
    "W-03-gap": "the second event is skipped: seq jumps from 1 to 3",
    "W-03-resume": "Last-Event-ID and ?after= are ignored; the stream always replays from 1",
    "W-04": "consumption is reported for every step at the end, just before assignment.finished",
    "W-05": "no step.boundary is ever emitted, although checkpoints are still written",
    "W-06": "a stop skips the boundary of the running step and reports the previous checkpoint",
    "W-07": "a call to the agent outside the frame's tools is made without refused: true",
    "W-08-event": "the value of the credential is written into a step.progress message",
    "W-08-artifact": "the value of the credential is written into an artifact",
    "W-08-log": "the value of the credential is written to the worker's log",
    "W-09": "tool.called carries the request in clear instead of its sha256",
    "W-10": "an estimate above the limits is accepted; the assignment fails after its first step",
    "W-11": "a resumed assignment produces the artifacts from before its checkpoint again",
    "W-13": "the agent's host outside allowed_hosts is reached without refused: true",
    "W-14": "the limits are ignored once running: steps keep starting after the total crossed them",
    "W-15": "an assignment beyond max_concurrent_assignments is accepted instead of answered 503",
    "W-16": "the state of an id never received is answered 200, accepted, instead of 404",
    "W-17": "an assignment whose id is held is accepted again as a second one instead of 409",
    "W-18": "the task's commands before and after the work are ignored",
    "W-19": "a steering message is received at once, inside the running step, not at a boundary",
}


def check_of(fault: str) -> str:
    return fault[:4]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log(message: str) -> None:
    sys.stderr.write(f"{now()} a2a-worker {message}\n")
    sys.stderr.flush()


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def text_of(message: Any) -> str:
    """The text parts of a protocol message, joined."""
    if not isinstance(message, dict):
        return ""
    parts = message.get("parts") or []
    texts = [
        str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("kind") == "text"
    ]
    return "\n".join(t for t in texts if t).strip()


# --- the agent ----------------------------------------------------------------------------------


class AgentError(Exception):
    """The agent could not be used: unreachable, a card or an answer the protocol does not
    describe, a JSON-RPC error. The message never carries the credential."""


@dataclass(frozen=True)
class Address:
    secure: bool
    hostname: str
    port: int
    path: str

    @classmethod
    def of(cls, url: str) -> Address:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"an http or https address is needed, not {url!r}")
        secure = parsed.scheme == "https"
        return cls(
            secure, parsed.hostname, parsed.port or (443 if secure else 80), parsed.path or "/"
        )

    def same_host(self, other: Address) -> bool:
        return (self.secure, self.hostname, self.port) == (other.secure, other.hostname, other.port)


class Agent:
    """One agent of the protocol, reached over its JSON-RPC binding."""

    def __init__(self, base: str, *, header: str, prefix: str) -> None:
        self.base = Address.of(base)
        url = urlparse(base)
        self.host = url.hostname if url.port is None else f"{url.hostname}:{url.port}"
        """The host the frame must allow, as the contract writes a host."""
        self.header = header
        self.prefix = prefix
        self.rpc: Address | None = None
        self.protocol: str | None = None
        self._ids = 0
        self._lock = threading.Lock()

    def _http(
        self, address: Address, method: str, path: str, token: str | None, body: Json | None
    ) -> Any:
        headers = {"Accept": "application/json"}
        if token is not None and self.header:
            headers[self.header] = self.prefix + token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        connection: http.client.HTTPConnection
        if address.secure:
            connection = http.client.HTTPSConnection(
                address.hostname, address.port, timeout=REQUEST_TIMEOUT
            )
        else:
            connection = http.client.HTTPConnection(
                address.hostname, address.port, timeout=REQUEST_TIMEOUT
            )
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as error:
            raise AgentError(
                f"the agent did not answer {method} {path}: {type(error).__name__}"
            ) from None
        finally:
            connection.close()
        if response.status >= 400:
            raise AgentError(f"the agent answered {method} {path} with {response.status}")
        try:
            return json.loads(raw or b"null")
        except ValueError:
            raise AgentError(f"the agent's answer to {method} {path} is not JSON") from None

    def card(self) -> Json:
        """Read the agent card, once, and the JSON-RPC address it names. An address on another
        host than the agent's, or a card that offers no JSON-RPC, is not used: the frame allows
        the agent's host, and nothing else is reached."""
        prefix = self.base.path.rstrip("/")
        card = self._http(self.base, "GET", prefix + CARD_PATH, None, None)
        if not isinstance(card, dict):
            raise AgentError("the agent card is not an object")
        offered = [(card.get("preferredTransport") or "JSONRPC", card.get("url"))]
        for interface in card.get("additionalInterfaces") or []:
            if isinstance(interface, dict):
                offered.append((interface.get("transport"), interface.get("url")))
        rpc = [url for transport, url in offered if transport == "JSONRPC" and url]
        if not rpc:
            raise AgentError("the agent card offers no JSON-RPC transport")
        try:
            address = Address.of(str(rpc[0]))
        except ValueError:
            raise AgentError("the agent card names no http address for JSON-RPC") from None
        if not address.same_host(self.base):
            raise AgentError("the agent card names another host for JSON-RPC; nothing was sent")
        self.rpc = address
        self.protocol = str(card.get("protocolVersion") or "unstated")
        return card

    def call(self, method: str, params: Json, token: str | None) -> Any:
        if self.rpc is None:
            self.card()
        if self.rpc is None:
            raise AgentError("the agent card named no JSON-RPC address")
        with self._lock:
            self._ids += 1
            request_id = self._ids
        answer = self._http(
            self.rpc,
            "POST",
            self.rpc.path,
            token,
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        )
        if not isinstance(answer, dict):
            raise AgentError(f"the agent's answer to {method} is not a JSON-RPC response")
        error = answer.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or "")[:200]
            raise AgentError(f"the agent answered {method} with error {error.get('code')} {detail}")
        if "result" not in answer:
            raise AgentError(f"the agent's answer to {method} carries no result")
        return answer["result"]

    def task(self, task_id: str, token: str | None) -> Json:
        result = self.call("tasks/get", {"id": task_id}, token)
        if not isinstance(result, dict) or result.get("kind", "task") != "task":
            raise AgentError("the agent's answer to tasks/get is not a task")
        return result


def status_of(task: Json) -> tuple[str, str, str]:
    """The task's state, a mark that changes whenever its status changes, and its message."""
    status = task.get("status") if isinstance(task.get("status"), dict) else {}
    state = str(status.get("state") or "unknown")
    message = status.get("message") if isinstance(status.get("message"), dict) else {}
    mark = f"{state}|{message.get('messageId', '')}|{status.get('timestamp', '')}"
    return state, mark, text_of(message)[:300]


def convert(artifact: Json, index: int) -> tuple[str, str, bytes]:
    """One artifact of the agent as an artifact of the assignment: its id, media type and
    bytes. A file the agent names by address is described, not fetched: the address may be on
    a host the frame does not allow."""
    raw_id = str(artifact.get("artifactId") or artifact.get("name") or index)
    artifact_id = "agent-" + re.sub(r"[^A-Za-z0-9_.-]", "-", raw_id)[:80]
    parts = [p for p in artifact.get("parts") or [] if isinstance(p, dict)]
    if parts and all(p.get("kind") == "text" for p in parts):
        return artifact_id, "text/plain", "\n".join(str(p.get("text", "")) for p in parts).encode()
    if len(parts) == 1 and parts[0].get("kind") == "data":
        return artifact_id, "application/json", json.dumps(parts[0].get("data")).encode()
    if len(parts) == 1 and parts[0].get("kind") == "file":
        file = parts[0].get("file") if isinstance(parts[0].get("file"), dict) else {}
        if isinstance(file.get("bytes"), str):
            try:
                content = base64.b64decode(file["bytes"], validate=True)
            except ValueError:
                content = b""
            return artifact_id, str(file.get("mimeType") or "application/octet-stream"), content
    return artifact_id, "application/json", json.dumps(parts, ensure_ascii=False).encode()


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
    task: str | None = None  # the agent's task
    context: str | None = None  # the agent's context of that task
    mark: str | None = None  # the status last seen
    seen: int = 0  # status changes seen
    turns: int = 0  # turn steps taken; a turn may end without a change (a stop, a message)
    ended: str | None = None  # the protocol's state that ended the task
    direct: list[Json] | None = None  # the parts of an answer given at once, without a task
    fetched: bool = False
    after: bool = False
    steps: int = 0
    summary: str | None = None  # the agent's last status message
    protocol: str | None = None

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
    calls: bool  # whether the step calls the agent, under the frame


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
    stop_at: float = 0.0
    stop_ceiling: float = STOP_CEILING
    pending: list[Json] = field(default_factory=list)
    """Steering messages accepted and not yet received: received at the next boundary."""
    received: list[Json] = field(default_factory=list)
    unforwarded: list[Json] = field(default_factory=list)
    """Messages received and not yet sent into the agent's task."""
    message_ids: set[str] = field(default_factory=set)
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
        self.agent = Agent(options.agent, header=options.auth_header, prefix=options.auth_prefix)
        self.capability: str = options.capability
        self.resource_class: str = options.resource_class
        self.credential: str | None = None if options.anonymous else options.credential
        self.state_dir = Path(options.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.assignments: dict[str, Assignment] = {}
        self.lock = threading.Lock()

    # -- declarations --

    def capabilities(self) -> Json:
        kinds = [] if self.fault == "W-01" else ["compute"]
        estimate = self._whole()
        if self.fault == "W-02-estimator":
            estimate = {**estimate, "compute_seconds": estimate["compute_seconds"] / 10}
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "data_location": self.options.stores,
            "capabilities": [self.capability],
            "consumption": {"kinds": kinds, "resource_classes": [self.resource_class]},
            "supports": {
                "native_pause": False,
                "steering": True,
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
        return 2 + self.options.estimate_turns + around

    def _whole(self) -> Json:
        """The estimate of a fresh assignment with a command before and after the work: what
        the declared estimator yields, never less than `estimate` answers (W-02)."""
        return {
            "confidence": "low",
            "compute_seconds": round(self.options.estimate_seconds, 3),
            "resource_class": self.resource_class,
            "wall_seconds": int(self.options.estimate_seconds) + 1,
            "steps": 2 + self.options.estimate_turns + 2,
        }

    def expected(self, following: Next) -> float:
        """A step's own expected demand: the estimate shared among the turns it expects. A
        call that sends or fetches is expected to take nothing of its own."""
        if following.kind != "turn":
            return 0.0
        return self.options.estimate_seconds / max(self.options.estimate_turns, 1)

    def estimate(self, request: Json) -> Json:
        task = request.get("task") or {}
        progress = Progress()
        ref = (request.get("context") or {}).get("checkpoint_ref")
        if ref:
            record = self._load_checkpoint(str(ref))
            if record is not None:
                progress = Progress.from_json(record["progress"])
        turns_left = max(self.options.estimate_turns - progress.seen, 0)
        if progress.ended:
            turns_left = 0
        fraction = turns_left / max(self.options.estimate_turns, 1)
        steps = self._steps_of(task) - progress.steps
        return {
            "confidence": "low",
            "compute_seconds": round(self.options.estimate_seconds * fraction, 3),
            "resource_class": self.resource_class,
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
        if self.credential is not None and self.credential not in names:
            return (
                f"the assignment references no credential {self.credential}, which the agent needs"
            )
        estimate = self.estimate(body)
        if self.fault != "W-10":
            compute = body["limits"].get("compute") or {}
            if compute.get("resource_class") != self.resource_class:
                return (
                    f"this worker consumes compute in {self.resource_class}, and the limits carry "
                    "no limit in it"
                )
            if estimate["compute_seconds"] > float(compute["seconds"]):
                return (
                    f"estimated {estimate['compute_seconds']:g}s of {self.resource_class} exceeds "
                    f"the limit of {float(compute['seconds']):g}s"
                )
        frame = body["frame"]
        if estimate["steps"] > frame["max_steps"]:
            return f"{estimate['steps']} steps needed, frame allows {frame['max_steps']}"
        deadline = frame.get("deadline")
        if deadline:
            until = deadline_of(deadline)
            if until is None:
                return f"deadline {deadline!r} is not a date-time"
            if until < time.time() + estimate["wall_seconds"]:
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

    def stop(self, assignment: Assignment, body: Any) -> Json:
        ceiling = (body or {}).get("ceiling_seconds") if isinstance(body, dict) else None
        with assignment.lock:
            if assignment.status != "finished":
                assignment.stop_requested = True
                assignment.stop_at = time.monotonic()
                if isinstance(ceiling, int) and ceiling >= 1:
                    assignment.stop_ceiling = float(ceiling)
                assignment.status = "stopping"
            return assignment.state()

    def steer(self, assignment: Assignment, body: Any) -> tuple[int, Json]:
        """Accept a steering message (W-19). It is received at the next boundary and sent into
        the agent's task at the start of the step after it. A message is an input: it changes
        neither the frame nor the limits."""
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("message_id"), str)
            or not re.match(r"^msg_[A-Za-z0-9_-]{4,}$", body["message_id"])
            or not isinstance(body.get("text"), str)
            or not 1 <= len(body["text"]) <= 8000
        ):
            return 400, {"title": "invalid message", "status": 400}
        with assignment.lock:
            if assignment.status == "finished":
                return 409, {
                    "title": "assignment finished",
                    "status": 409,
                    "detail": "a finished assignment receives no message",
                }
            message_id = str(body["message_id"])
            if message_id in assignment.message_ids:
                return 202, assignment.state()
            assignment.message_ids.add(message_id)
            message = {"message_id": message_id, "text": str(body["text"])}
            if self.fault == "W-19":
                # the W-19 fault: received at once, inside the step that is running
                state = assignment.state()
                assignment.received.append(message)
                assignment.unforwarded.append(message)
                self._emit(assignment, {"type": "message.received", "message_id": message_id})
                return 202, state
            assignment.pending.append(message)
            return 202, assignment.state()

    def _receive(self, assignment: Assignment, step_id: str | None) -> None:
        """Receive every message accepted since the last boundary, at this one. Caller holds
        the assignment's lock."""
        for message in assignment.pending:
            event: Json = {"type": "message.received", "message_id": message["message_id"]}
            if step_id is not None:
                event["step_id"] = step_id
            self._emit(assignment, event)
            assignment.received.append(message)
            assignment.unforwarded.append(message)
        assignment.pending.clear()

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
        if progress.task is None and progress.ended is None:
            return Next("send", "send", "send the task to the agent", True)
        if progress.ended is None:
            return Next(
                f"turn-{progress.turns + 1}", "turn", "wait for the agent's next status", True
            )
        if not progress.fetched:
            return Next("fetch", "fetch", "fetch the agent's artifacts", progress.task is not None)
        if isinstance(task.get("after"), dict) and not progress.after and self.fault != "W-18":
            return Next("after", "shell", "the command after the work", False)
        return None

    def _run(self, assignment: Assignment) -> None:
        frame = assignment.body["frame"]
        token = os.environ.get(self.credential) if self.credential else None
        if self.credential:
            log(f"credential {self.credential}: {'present' if token else 'absent'}")
        deferred: list[Json] = []
        used = 0.0  # the compute this assignment has reported so far: its running total
        last_checkpoint: str | None = (assignment.body.get("context") or {}).get("checkpoint_ref")
        previous: str | None = None
        workspace = self.state_dir / "workspaces" / assignment.id
        workspace.mkdir(parents=True, exist_ok=True)
        with assignment.lock:
            assignment.status = "running" if not assignment.stop_requested else "stopping"
            assignment.started_at = now()
            if self.fault == "W-11":
                for produced in assignment.inherited:
                    assignment.produced.append(produced)
                    self._emit(assignment, artifact_event(assignment, produced, None))
        while (step := self._next(assignment)) is not None:
            began = time.monotonic()
            with assignment.lock:
                if assignment.progress.steps >= int(frame["max_steps"]):
                    self._finish(
                        assignment,
                        "failed",
                        reason=f"the frame's max_steps of {frame['max_steps']} is reached",
                    )
                    return
                # A message accepted since the last boundary is received here, before the step
                # starts, so that the step has it (W-19).
                self._receive(assignment, previous)
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
            if step.calls:
                failure = self._held(assignment, step, frame)
            if failure is None:
                try:
                    failure = self._do(assignment, step, token, workspace, frame)
                except AgentError as error:
                    failure = f"step {step.step_id!r}: {error}"
            if self.fault == "W-08-log" and token:
                log(f"credential {self.credential}={token}")  # the W-08-log fault
            if self.fault == "W-08-event" and token:
                with assignment.lock:
                    self._emit(
                        assignment,
                        {
                            "type": "step.progress",
                            "step_id": step.step_id,
                            "message": f"using {self.credential}={token}",  # the fault
                        },
                    )
            assignment.progress.steps += 1
            remaining = 0.01 - (time.monotonic() - began)
            if remaining > 0:
                time.sleep(remaining)
            seconds = round(time.monotonic() - began, 3)
            consumption: Json = {
                "type": "consumption.reported",
                "step_id": step.step_id,
                "compute_seconds": seconds,
                "resource_class": self.resource_class,
            }
            used += seconds
            previous = step.step_id
            with assignment.lock:
                if self.fault == "W-04":
                    deferred.append(consumption)
                else:
                    self._emit(assignment, consumption)
                # The W-06 fault needs a boundary before the one it skips, to report instead.
                w06 = self.fault == "W-06" and assignment.stop_requested
                skip_boundary = w06 and last_checkpoint is not None
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
                    compute = assignment.body["limits"].get("compute") or {}
                    if "seconds" in compute and self._whole()["compute_seconds"] > float(
                        compute["seconds"]
                    ):
                        self._finish(assignment, "failed", reason="limits exceeded after starting")
                        return
                if assignment.stop_requested and (not w06 or skip_boundary):
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
                            limit="compute",
                        )
                        return
        with assignment.lock:
            for consumption in deferred:
                self._emit(assignment, consumption)
            self._finish(assignment, "succeeded", summary="the agent's artifacts are fetched")

    def _held(self, assignment: Assignment, step: Next, frame: Json) -> str | None:
        """The step's calls to the agent, held against the frame: reported as `tool.called`
        with the agent's host, refused visibly where the frame does not allow the capability
        or the host (W-07, W-13). The reason, or None when the calls may be made."""
        request = f"{step.kind} {self.agent.host} {assignment.progress.task or ''}"
        call: Json = {
            "type": "tool.called",
            "step_id": step.step_id,
            "tool": self.capability,
            "host": self.agent.host,
            "arguments_digest": request if self.fault == "W-09" else sha256(request.encode()),
        }
        reason = None
        if self.capability not in frame.get("allowed_tools", []) and self.fault != "W-07":
            reason = f"{self.capability} is outside the frame's allowed_tools"
        elif self.agent.host not in (frame.get("allowed_hosts") or []) and self.fault != "W-13":
            reason = f"{self.agent.host} is not in the frame's allowed_hosts"
        if reason is not None:
            call["refused"] = True
            call["reason"] = reason
        with assignment.lock:
            self._emit(assignment, call)
        return None if reason is None else f"step {step.step_id!r}: {reason}; nothing was sent"

    def _progress(self, assignment: Assignment, step: Next, message: str) -> None:
        with assignment.lock:
            self._emit(
                assignment,
                {"type": "step.progress", "step_id": step.step_id, "message": message},
            )

    def _do(
        self, assignment: Assignment, step: Next, token: str | None, workspace: Path, frame: Json
    ) -> str | None:
        """Carry out one step: why it failed, if it did."""
        progress, task = assignment.progress, assignment.task
        if step.step_id in ("before", "after"):
            self._not_forwarded(assignment, step)
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
            return failure
        if step.kind == "send":
            return self._send(assignment, step, token)
        if step.kind == "turn":
            return self._turn(assignment, step, token, frame)
        return self._fetch(assignment, step, token)

    def _send(self, assignment: Assignment, step: Next, token: str | None) -> str | None:
        progress, task = assignment.progress, assignment.task
        self.agent.card()
        progress.protocol = self.agent.protocol
        brief = str(task.get("goal", ""))
        acceptance = [str(a) for a in task.get("acceptance") or []]
        if acceptance:
            brief += "\n\nAccepted when:\n" + "\n".join(f"- {a}" for a in acceptance)
        parts: list[Json] = [{"kind": "text", "text": brief}]
        if task.get("inputs"):
            parts.append({"kind": "data", "data": task["inputs"]})
        with assignment.lock:
            messages, assignment.unforwarded = list(assignment.unforwarded), []
        parts.extend({"kind": "text", "text": m["text"]} for m in messages)
        message = {
            "kind": "message",
            "role": "user",
            "messageId": f"{assignment.id}-task",
            "parts": parts,
        }
        result = self.agent.call(
            "message/send", {"message": message, "configuration": {"blocking": False}}, token
        )
        if not isinstance(result, dict):
            raise AgentError("the agent's answer to message/send is neither a task nor a message")
        if result.get("kind") == "message":
            progress.direct = [p for p in result.get("parts") or [] if isinstance(p, dict)]
            progress.ended = "completed"
            progress.summary = text_of(result) or None
            self._progress(assignment, step, "the agent answered at once, without a task")
        else:
            if not isinstance(result.get("id"), str) or not result["id"]:
                raise AgentError("the agent's task names no id")
            progress.task = result["id"]
            progress.context = result.get("contextId")
            state, mark, text = status_of(result)
            progress.mark = mark
            progress.summary = text or progress.summary
            if state in ENDED:
                progress.ended = state
        record = {
            "agent_task": progress.task,
            "agent": self.agent.host,
            "protocol": progress.protocol,
            "stores": self.options.stores,
        }
        self._produce(
            assignment,
            step,
            "agent-task",
            "a2a.task",
            "application/json",
            json.dumps(record).encode(),
        )
        if progress.ended is not None and ENDED[progress.ended] == "failed":
            return f"the agent's task ended {progress.ended}: {progress.summary or 'no reason'}"
        return None

    def _turn(
        self, assignment: Assignment, step: Next, token: str | None, frame: Json
    ) -> str | None:
        progress = assignment.progress
        if progress.task is None:
            raise AgentError("the agent's task is not known")
        progress.turns += 1
        with assignment.lock:
            messages, assignment.unforwarded = list(assignment.unforwarded), []
        for message in messages:
            self._forward(assignment, step, message, token)
        deadline = deadline_of(frame.get("deadline"))
        while True:
            found = self.agent.task(progress.task, token)
            state, mark, text = status_of(found)
            if mark != progress.mark:
                progress.mark = mark
                progress.seen += 1
                progress.summary = text or progress.summary
                if state in ENDED:
                    progress.ended = state
                if state == "input-required":
                    summary = f"the agent asks for input: {text or 'no question given'}"
                else:
                    summary = text or f"the agent's task is {state}"
                break
            with assignment.lock:
                paused = (
                    assignment.stop_requested
                    and time.monotonic() - assignment.stop_at >= assignment.stop_ceiling
                )
                answered = state in WAITING and bool(assignment.pending)
            if answered:
                # The agent waits for input and a message waits for the boundary: the turn
                # ends here, the message is received at its boundary and sent into the task
                # by the next turn (W-19).
                summary = "the agent waits for input; the message waiting is sent next"
                break
            if paused:
                summary = "the observation paused at the stop's ceiling; the agent works on"
                break
            if deadline is not None and time.time() > deadline:
                return f"the frame's deadline passed while the agent's task was {state}"
            time.sleep(self.options.poll_seconds)
        self._progress(assignment, step, summary)
        if progress.ended is not None and ENDED[progress.ended] == "failed":
            return f"the agent's task ended {progress.ended}: {progress.summary or 'no reason'}"
        return None

    def _forward(
        self, assignment: Assignment, step: Next, message: Json, token: str | None
    ) -> None:
        """Send a received message into the agent's task, as a further message of it."""
        progress = assignment.progress
        request = f"forward {self.agent.host} {progress.task} {message['message_id']}"
        with assignment.lock:
            self._emit(
                assignment,
                {
                    "type": "tool.called",
                    "step_id": step.step_id,
                    "tool": self.capability,
                    "host": self.agent.host,
                    "arguments_digest": sha256(request.encode()),
                },
            )
        further: Json = {
            "kind": "message",
            "role": "user",
            "messageId": message["message_id"],
            "taskId": progress.task,
            "parts": [{"kind": "text", "text": message["text"]}],
        }
        if progress.context:
            further["contextId"] = progress.context
        try:
            self.agent.call("message/send", {"message": further}, token)
        except AgentError as error:
            self._progress(
                assignment, step, f"the agent did not take message {message['message_id']}: {error}"
            )
            return
        self._progress(assignment, step, f"sent message {message['message_id']} to the agent")

    def _not_forwarded(self, assignment: Assignment, step: Next) -> None:
        """Messages received after the agent's task ended reach no step of the agent."""
        if assignment.progress.ended is None:
            return
        with assignment.lock:
            messages, assignment.unforwarded = list(assignment.unforwarded), []
        for message in messages:
            self._progress(
                assignment,
                step,
                f"message {message['message_id']} was not sent: the agent's task has ended",
            )

    def _fetch(self, assignment: Assignment, step: Next, token: str | None) -> str | None:
        progress = assignment.progress
        self._not_forwarded(assignment, step)
        if progress.direct is not None:
            artifacts = [{"artifactId": "answer", "parts": progress.direct}]
        else:
            if progress.task is None:
                raise AgentError("the agent's task is not known")
            found = self.agent.task(progress.task, token)
            artifacts = [a for a in found.get("artifacts") or [] if isinstance(a, dict)]
            _, _, text = status_of(found)
            progress.summary = text or progress.summary
        taken: set[str] = set()
        for index, artifact in enumerate(artifacts):
            artifact_id, media_type, content = convert(artifact, index)
            while artifact_id in taken:
                artifact_id += "-again"
            taken.add(artifact_id)
            self._produce(assignment, step, artifact_id, "agent.output", media_type, content)
        summary = progress.summary or "The agent completed the task."
        self._produce(assignment, step, "summary", "report", "text/plain", summary.encode())
        progress.fetched = True
        return None

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
        token = os.environ.get(self.credential) if self.credential else None
        if self.fault == "W-08-artifact" and token and step.step_id not in ("before", "after"):
            content += f"\n{self.credential}={token}\n".encode()  # the W-08 fault
        produced = Produced(artifact_id, kind, media_type, content)
        with assignment.lock:
            assignment.produced.append(produced)
            self._emit(assignment, artifact_event(assignment, produced, step.step_id))

    def _over_ceiling(self, body: Json, used: float, following: Next) -> str | None:
        """The limits are this worker's hard ceiling (W-14): the next step does not start when
        the running total and that step's expected demand would exceed the compute limit."""
        compute = body["limits"].get("compute") or {}
        if "seconds" not in compute:
            return None
        ceiling = float(compute["seconds"])
        expected = self.expected(following)
        if used >= ceiling or used + expected > ceiling:
            return (
                f"the running total of {used:g}s and the {expected:g}s the step "
                f"{following.step_id!r} expects would exceed the limit of {ceiling:g}s of "
                f"{self.resource_class}; halted at the boundary"
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
        """Caller holds the assignment's lock. A message still waiting is received first: it
        was accepted while the assignment ran (W-19)."""
        self._receive(assignment, None)
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


def deadline_of(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def artifact_event(assignment: Assignment, produced: Produced, step_id: str | None) -> Json:
    event: Json = {"type": "artifact.produced", **produced.describe(assignment.id)}
    event["artifact_id"] = event.pop("id")
    if step_id is not None:
        event["step_id"] = step_id
    return event


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
                self._json(202, self.worker.stop(assignment, body))
        elif len(parts) == 4 and parts[:2] == ["v1", "assignments"] and parts[3] == "messages":
            if (assignment := self._assignment(parts[2])) is not None:
                status, response = self.worker.steer(assignment, body)
                kind = "application/json" if status == 202 else "application/problem+json"
                self._json(status, response, kind)
        elif len(parts) == 4 and parts[:2] == ["v1", "assignments"] and parts[3] == "handover":
            if self._assignment(parts[2]) is not None:
                self._problem(
                    400, "handover not offered", "this worker does not declare handover (ADR-0172)"
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
    # agent, its capability and where it stores through the unit's environment (ADR-0090).
    port = int(os.environ.get("TAKTUS_UNIT_PORT") or 9030)
    state_dir = os.environ.get("TAKTUS_UNIT_STATE_DIR") or None
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument(
        "--agent",
        default=os.environ.get("A2A_AGENT_URL"),
        help="the agent's address, where its agent card is served (A2A_AGENT_URL)",
    )
    parser.add_argument(
        "--capability",
        default=os.environ.get("A2A_AGENT_CAPABILITY"),
        help="what the agent does, by function: lowercase dotted (A2A_AGENT_CAPABILITY); required",
    )
    parser.add_argument(
        "--stores",
        choices=LOCATIONS,
        default=os.environ.get("A2A_AGENT_STORES") or None,
        help="where the agent keeps what it is sent: own, eu or elsewhere (A2A_AGENT_STORES); "
        "required, nothing is assumed",
    )
    parser.add_argument(
        "--credential",
        default=DEFAULT_CREDENTIAL,
        help="the name of the credential the agent is reached with",
    )
    parser.add_argument(
        "--anonymous", action="store_true", help="the agent is reached without a credential"
    )
    parser.add_argument("--auth-header", default="Authorization", help="the credential's header")
    parser.add_argument("--auth-prefix", default="Bearer ", help="what precedes the credential")
    parser.add_argument(
        "--resource-class",
        default=DEFAULT_RESOURCE_CLASS,
        help="the resource class the seconds the agent works on a task are reported in",
    )
    parser.add_argument(
        "--estimate-seconds",
        type=float,
        default=600.0,
        help="the expected seconds the agent works on a task",
    )
    parser.add_argument(
        "--estimate-turns",
        type=int,
        default=3,
        help="the status changes a task is expected to take",
    )
    parser.add_argument(
        "--poll-seconds", type=float, default=2.0, help="how often the agent's task is read"
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
    if not args.agent:
        parser.error("--agent is required: the agent's address")
    try:
        Address.of(args.agent)
    except ValueError as error:
        parser.error(f"--agent: {error}")
    if not args.capability or not CAPABILITY.fullmatch(args.capability):
        parser.error("--capability is required: lowercase dotted segments, at least two")
    if args.stores is None:
        parser.error("--stores is required: own, eu or elsewhere; nothing is assumed")
    if args.estimate_seconds <= 0 or args.estimate_turns < 1:
        parser.error("--estimate-seconds must be above 0 and --estimate-turns at least 1")
    if args.max_concurrent < 1:
        parser.error("--max-concurrent must be at least 1")
    if args.state_dir is None:
        args.state_dir = str(Path.home() / ".cache" / "taktus-a2a-worker" / secrets.token_hex(4))
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
        f"listening on http://{args.host}:{server.server_port}, agent "
        f"{Handler.worker.agent.host}, capability {args.capability}, stores {args.stores}{fault}"
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
