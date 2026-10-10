#!/usr/bin/env python3
"""The second coding worker: a second vendor's coding agent behind the worker contract v1.

The agent is Codex (`codex exec --json`), driven in its documented non-interactive mode; this
directory is the only place in the repository that names it, and the control plane knows it as
a worker offering `code.read`, `code.edit`, `code.test` and `shell.sandboxed` — the
capabilities of the first coding worker, `workers/claudecode/`, that a coding step requires. A
step served by either is served by the other (README.md in this directory says how far):

- **step boundaries**: every item of the agent's stream that acts — a command it runs, a
  change it makes to files — is one step; when the item completes, the workspace is committed
  and a checkpoint written — the agent's thread and the commit — and `step.boundary` is
  emitted. A stop lands there; a resumed assignment continues the same thread in the same
  workspace and announces no artifact twice;
- **consumption per step**: the agent writes the tokens of every model response into its
  session file before it acts on that response. The worker reads the running total there and
  reports the difference with the step the response started; whatever the session file did
  not show is settled with the last step, from the total the agent reports for its turn. The
  agent reports no money: the tokens are reported per model and per price kind, and money
  follows from them and a price table;
- **the limits as a ceiling**: at every boundary the running total is held against the limits;
  once a limit of tokens or quota is reached, the agent is ended there and the assignment ends
  `stopped` with the checkpoint and the limit named;
- **authentication**: by API key or by the agent's login file, chosen at start (`--auth`) and
  supplied under the credential name the assignment carries; a login that expires mid-run, or
  a window that is exhausted, halts at the last boundary with the cause;
- **the frame**: the agent has no permission per call in its non-interactive mode. The frame
  chooses its sandbox — read-only unless the frame allows changing anything, no network unless
  the frame allows a host — and every item is held against the frame when it appears. An item
  outside it is emitted as `tool.called` with `refused: true`, the agent is ended, whatever the
  item left in the workspace is reset to the last boundary, and the assignment fails.

Fault injection (`--fault NAME`) makes this worker violate exactly one conformance check, so
that the suite can be shown to catch it here too. `--agent` names the agent's command line; the
gate runs this worker against `fake_agent.py`, which writes the same stream and the same session
file, so that the contract's mechanics are proven without an account and every fault is
deterministic.

This file imports nothing from src/taktus, and nothing from the first coding worker. It is a
separate deployable, as every worker is: removing one coding worker must not touch the other.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
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
MAX_CONCURRENT = 2
AGENT_EXIT_GRACE = 10.0
DEFAULT_CEILING = 300
AFTER_TIMEOUT = 300  # seconds the task's command after the work may run

CAPABILITIES = ["code.read", "code.edit", "code.test", "shell.sandboxed"]
# What changes the workspace: the agent's sandbox is writable only when the frame allows one.
WRITING = frozenset({"code.edit", "code.test", "shell.sandboxed"})
STEP_KIND = {"code.read": "read", "code.edit": "edit", "code.test": "shell"}
TEST_COMMAND = re.compile(r"\b(pytest|npm test|npm run test|make test|go test|cargo test)\b")
# A command that only reads: every part of it is one of these programs, and nothing redirects
# into a file or substitutes a command. `sed` reads only with `-n`.
READING = frozenset({"cat", "head", "tail", "ls", "rg", "grep", "wc", "nl", "pwd", "stat", "tree"})
WRITES = re.compile(r">|\$\(|`|\btee\b")
SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
AUTH_VARIABLE = {"api-key": "CODEX_API_KEY", "session": "auth.json"}
BASELINE_TAG = "taktus-baseline"
# The names a coding step references its credential by. They are the first coding worker's, so
# that a process runs unchanged on either; the value each worker receives is its own agent's.
DEFAULT_CREDENTIAL = {"api-key": "CODING_AGENT_API_KEY", "session": "CODING_AGENT_SESSION"}
AUTH_FAILURE = re.compile(
    r"\b401\b|unauthori[sz]ed|invalid api key|incorrect api key|not logged in|log ?in again|"
    r"authentication|token (?:has )?expired|refresh token",
    re.IGNORECASE,
)
WINDOW = re.compile(r"usage limit|hit your limit", re.IGNORECASE)

FAULTS: dict[str, str] = {
    "W-01": "capabilities declares no consumption kind",
    "W-02": "estimate answers 501 instead of an estimate",
    "W-03-gap": "the second event is skipped: seq jumps from 1 to 3",
    "W-03-resume": "Last-Event-ID and ?after= are ignored; the stream always replays from 1",
    "W-04": "consumption is reported for every step at the end, just before assignment.finished",
    "W-05": "no step.boundary is ever emitted, although checkpoints are still written",
    "W-06": "a stop skips the boundary of the running step and reports the previous checkpoint",
    "W-07": "the frame is not held: the sandbox is writable and no item is refused",
    "W-08-event": "the value of the first credential is written into a step.progress message",
    "W-08-artifact": "the value of the first credential is written into an artifact",
    "W-08-log": "the value of the first credential is written to the worker's log",
    "W-09": "tool.called carries the tool's arguments in clear instead of their sha256",
    "W-10": "an estimate above the limits is accepted; the assignment fails after its first step",
    "W-11": "a resumed assignment produces the artifacts from before its checkpoint again",
    "W-13": "a host outside allowed_hosts is reached and reported without refused: true",
    "W-14": "the limits are ignored once running: the agent goes on after the total reached them",
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
    sys.stderr.write(f"{now()} second-coding-worker {message}\n")
    sys.stderr.flush()


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_of(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


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
class Assignment:
    body: Json
    lineage: str
    """The assignment id the chain of checkpoints started with: the workspace's name."""
    session_id: str
    """The agent's thread, once the agent named it; empty before."""
    step_index: int
    """Steps completed before this assignment started, from the checkpoint it resumes."""
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
    stop_ceiling: int = DEFAULT_CEILING
    seq: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    changed: threading.Condition = field(init=False)
    agent: subprocess.Popen[str] | None = None

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
        for name in ("outcome", "checkpoint_ref", "reason", "started_at", "finished_at"):
            if getattr(self, name) is not None:
                state[name] = getattr(self, name)
        return state


@dataclass
class Tokens:
    """Tokens by the kinds a provider prices differently. `input` is every input token, the
    cached ones included, as the agent counts it."""

    input: int = 0
    cached: int = 0
    cache_write: int = 0
    output: int = 0

    def minus(self, other: Tokens) -> Tokens:
        return Tokens(
            max(0, self.input - other.input),
            max(0, self.cached - other.cached),
            max(0, self.cache_write - other.cache_write),
            max(0, self.output - other.output),
        )

    def plus(self, other: Tokens) -> Tokens:
        return Tokens(
            self.input + other.input,
            self.cached + other.cached,
            self.cache_write + other.cache_write,
            self.output + other.output,
        )


@dataclass
class Step:
    """One item of the agent's stream that acts, from its appearance to its completion."""

    index: int
    step_id: str
    tool: str
    capability: str
    kind: str
    tokens: Tokens
    began: float
    item_id: str | None = None
    refused: bool = False


# --- the worker ---------------------------------------------------------------------------------


class Worker:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.fault: str | None = options.fault
        self.auth: str = options.auth
        self.credential_name: str = options.credential or DEFAULT_CREDENTIAL[options.auth]
        self.agent_command: list[str] = shlex.split(options.agent)
        self.state_dir = Path(options.state_dir)
        for sub in ("checkpoints", "workspaces", "agent"):
            (self.state_dir / sub).mkdir(parents=True, exist_ok=True)
        self.assignments: dict[str, Assignment] = {}
        self.lock = threading.Lock()
        # One login file at a time: the agent's home is shared by the assignments of this
        # worker, so that a thread outlives the assignment that started it.
        self.login = threading.Lock()
        self.logged_in = 0

    # -- declarations --

    def capabilities(self) -> Json:
        if self.fault == "W-01":
            consumption: Json = {"kinds": []}
        elif self.auth == "api-key":
            consumption = {"kinds": ["currency"], "currencies": [self.options.currency]}
        else:
            consumption = {"kinds": ["quota"], "window_seconds": 18000, "unit": "steps"}
        return {
            "contract": CONTRACT,
            "version": VERSION,
            "capabilities": CAPABILITIES,
            "consumption": consumption,
            "supports": {
                "native_pause": False,
                "step_boundary_signal": True,
                "streaming_events": True,
                "estimate": True,
            },
            "max_concurrent_assignments": MAX_CONCURRENT,
        }

    def estimate(self, request: Json) -> Json:
        """Rough by nature — an agent's demand depends on the task — and honest about it:
        confidence low, the configured expectation of one assignment."""
        o = self.options
        estimate: Json = {
            "confidence": "low",
            "tokens_in": o.estimate_tokens_in,
            "tokens_out": o.estimate_tokens_out,
            "wall_seconds": o.estimate_wall_seconds,
            "steps": o.estimate_steps,
        }
        if self.auth == "api-key":
            estimate["currency"] = {o.currency: o.estimate_currency}
        else:
            estimate["quota_units"] = o.estimate_steps
        return estimate

    # -- checkpoints --

    def _checkpoint_path(self, ref: str) -> Path:
        return self.state_dir / "checkpoints" / (re.sub(r"[^A-Za-z0-9_.-]", "_", ref) + ".json")

    def _write_checkpoint(self, assignment: Assignment, index: int, commit: str | None) -> str:
        ref = f"ckpt/{assignment.lineage}/{index}"
        record = {
            "lineage": assignment.lineage,
            "session_id": assignment.session_id,
            "index": index,
            "commit": commit,
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
        record: Json = json.loads(path.read_text(encoding="utf-8"))
        return record

    # -- assignments --

    def accept(self, body: Json) -> tuple[int, Json]:
        problem = validate_assignment(body)
        if problem:
            return 400, {"title": "invalid assignment", "status": 400, "detail": problem}
        assignment_id = str(body["assignment_id"])
        with self.lock:
            if assignment_id in self.assignments and self.fault != "W-17":
                return 409, {"title": "assignment exists", "status": 409}
            running = sum(1 for a in self.assignments.values() if a.status != "finished")
            if running >= MAX_CONCURRENT and self.fault != "W-15":
                return 503, {"title": "at capacity", "status": 503}
            ref = body.get("context", {}).get("checkpoint_ref")
            lineage, session_id, index = assignment_id, "", 0
            inherited: list[Produced] = []
            rejection: str | None = None
            if ref:
                record = self._load_checkpoint(ref)
                if record is None:
                    rejection = f"unknown checkpoint {ref}"
                else:
                    lineage = str(record["lineage"])
                    session_id = str(record["session_id"] or "")
                    index = int(record["index"])
                    inherited = [
                        Produced(
                            p["artifact_id"],
                            p["kind"],
                            p["media_type"],
                            base64.b64decode(p["content"]),
                        )
                        for p in record["produced"]
                    ]
            assignment = Assignment(body, lineage, session_id, index, inherited)
            if rejection is None:
                rejection = self._does_not_fit(body)
            self.assignments[assignment_id] = assignment
            if rejection is not None:
                self._reject(assignment, rejection)
                return 201, assignment.state()
        threading.Thread(target=self._run, args=(assignment,), daemon=True).start()
        return 201, assignment.state()

    def _does_not_fit(self, body: Json) -> str | None:
        """Before anything starts: the credential the configured authentication needs is
        present, the estimate fits the limits, the frame can be honoured."""
        named = {c.get("name") for c in body.get("credentials") or []}
        if self.credential_name not in named:
            return (
                f"authentication {self.auth!r} needs the credential {self.credential_name}, "
                "which the assignment does not reference"
            )
        if self.credential_name not in os.environ:
            return (
                f"authentication {self.auth!r} needs the credential {self.credential_name}, "
                "which is not present in this worker's environment"
            )
        estimate = self.estimate(body)
        limits = body["limits"]
        if self.fault != "W-10":
            if self.auth == "api-key":
                currency = limits.get("currency") or {}
                code = self.options.currency
                if code not in currency:
                    return f"this worker consumes currency in {code}, and the limits carry none"
                if estimate["currency"][code] > currency[code]:
                    return (
                        f"estimated {estimate['currency'][code]} {code} exceeds the limit of "
                        f"{currency[code]} {code}"
                    )
            else:
                quota = limits.get("quota")
                if quota is None:
                    return "this worker consumes quota, and the limits carry no quota limit"
                if estimate["quota_units"] > quota["units"]:
                    return f"estimated {estimate['quota_units']} steps exceed {quota['units']}"
            for direction in ("in", "out"):
                ceiling = (limits.get("tokens") or {}).get(direction)
                if ceiling is not None and estimate[f"tokens_{direction}"] > ceiling:
                    return (
                        f"estimated {estimate[f'tokens_{direction}']} tokens {direction} exceed "
                        f"the limit of {ceiling}"
                    )
        frame = body["frame"]
        if estimate["steps"] > frame["max_steps"]:
            return f"{estimate['steps']} steps estimated, frame allows {frame['max_steps']}"
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
                ceiling = request.get("ceiling_seconds")
                if isinstance(ceiling, int) and ceiling > 0:
                    assignment.stop_ceiling = ceiling
            return assignment.state()

    # -- events --

    def _emit(self, assignment: Assignment, event: Json) -> Json:
        """Append one event. Caller holds the assignment's lock."""
        assignment.seq += 1
        if self.fault == "W-03-gap" and assignment.seq == 2:
            assignment.seq = 3
        full = {"assignment_id": assignment.id, "seq": assignment.seq, "ts": now(), **event}
        assignment.events.append(full)
        assignment.changed.notify_all()
        return full

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
        with assignment.lock:
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

    # -- the run --

    def _run(self, assignment: Assignment) -> None:
        run = _Run(self, assignment)
        try:
            run.execute()
        except Exception as error:  # a fault of this worker is a failed assignment, not a hang
            log(f"assignment {assignment.id} crashed: {error!r}")
            if assignment.status != "finished":
                self._finish(assignment, "failed", reason=f"the worker failed: {error!r}")

    def credential_value(self) -> str:
        return os.environ[self.credential_name]

    @property
    def agent_home(self) -> Path:
        return self.state_dir / "agent"

    def log_in(self) -> None:
        """In `session` mode the credential is the agent's login file. It is written into the
        agent's home, readable by this worker's user alone, for as long as an assignment runs,
        and removed when the last one ends (`log_out`)."""
        if self.auth != "session":
            return
        with self.login:
            self.logged_in += 1
            path = self.agent_home / AUTH_VARIABLE["session"]
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(self.credential_value())

    def log_out(self) -> None:
        if self.auth != "session":
            return
        with self.login:
            self.logged_in -= 1
            if self.logged_in <= 0:
                self.logged_in = 0
                (self.agent_home / AUTH_VARIABLE["session"]).unlink(missing_ok=True)


class _Run:
    """One assignment's execution: the workspace, the agent process, the events."""

    def __init__(self, worker: Worker, assignment: Assignment) -> None:
        self.worker = worker
        self.a = assignment
        self.body = assignment.body
        self.frame: Json = self.body["frame"]
        self.fault = worker.fault
        self.workspace = worker.state_dir / "workspaces" / assignment.lineage
        self.index = assignment.step_index
        self.last_checkpoint: str | None = self.body.get("context", {}).get("checkpoint_ref")
        self.deferred: list[Json] = []
        # The agent's session file, and the running total it showed when this run began and
        # when a step last took its tokens from it.
        self.session_file: Path | None = None
        self.baseline = Tokens()
        self.attributed = Tokens()
        self.model: str | None = worker.options.model
        # What this assignment has consumed so far, per quantity the limits can bound.
        self.used: dict[str, float] = {"tokens_in": 0.0, "tokens_out": 0.0, "quota_units": 0.0}
        self.halted: tuple[str, str] | None = None  # the limit kind and why
        self.current: Step | None = None
        self.last_step_id: str | None = None
        self.last_text = ""
        self.turn: Json | None = None
        self.failure: str | None = None

    # -- setup --

    def execute(self) -> None:
        a = self.a
        with a.lock:
            a.status = "running"
            a.started_at = now()
            if self.fault == "W-11":
                for produced in a.inherited:
                    a.produced.append(produced)
                    self.worker._emit(a, _artifact_event(a, produced, None))
        log(f"assignment {a.id} started at step {self.index + 1} (lineage {a.lineage})")
        if not self._prepare_workspace():
            return
        if not self._hosts_admitted():
            return
        self.worker.log_in()
        try:
            self._run_agent()
        finally:
            self.worker.log_out()

    def _prepare_workspace(self) -> bool:
        resuming = self.body.get("context", {}).get("checkpoint_ref") is not None
        if resuming and self.workspace.is_dir():
            return True
        self.workspace.mkdir(parents=True, exist_ok=True)
        workspace = self.body.get("context", {}).get("workspace") or {}
        if workspace.get("kind") == "git" and workspace.get("location"):
            location = str(workspace["location"])
            ref = workspace.get("ref")
            command = [
                "git",
                "clone",
                "--quiet",
                *(["--branch", ref] if ref else []),
                location,
                ".",
            ]
            completed = self._git(command, check=False)
            if completed.returncode != 0:
                self.worker._finish(
                    self.a,
                    "failed",
                    reason=f"the workspace could not be cloned: {completed.stderr.strip()[:200]}",
                )
                return False
        if not (self.workspace / ".git").is_dir():
            self._git(["git", "init", "--quiet"])
        self._git(["git", "add", "-A"])
        self._git(["git", "commit", "--quiet", "--allow-empty", "-m", "taktus: baseline"])
        # The baseline is tagged so that the changeset at the end is measured from it, also
        # after a resume in the same workspace.
        self._git(["git", "tag", "--force", BASELINE_TAG], check=False)
        return True

    def _git(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = {
            **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR")},
            "GIT_AUTHOR_NAME": "taktus",
            "GIT_AUTHOR_EMAIL": "taktus@localhost",
            "GIT_COMMITTER_NAME": "taktus",
            "GIT_COMMITTER_EMAIL": "taktus@localhost",
            "GIT_TERMINAL_PROMPT": "0",
        }
        return subprocess.run(  # noqa: S603 — git with fixed arguments in the workspace
            command, cwd=self.workspace, env=env, capture_output=True, text=True, check=check
        )

    def _hosts_admitted(self) -> bool:
        """The hosts the task says it needs, held against the frame before the agent starts,
        as a step of their own: reached later, or refused now — never reached in silence
        (W-13). The agent reaches a host from a command it runs, so reaching one is
        `shell.sandboxed`, which the frame must allow too (W-07)."""
        hosts = hosts_of(self.body["task"])
        if not hosts:
            return True
        self.index += 1
        step = Step(
            index=self.index,
            step_id=f"step-{self.index}",
            tool="hosts",
            capability="shell.sandboxed",
            kind="plan",
            tokens=Tokens(),
            began=time.monotonic(),
        )
        with self.a.lock:
            self.worker._emit(
                self.a,
                {
                    "type": "step.started",
                    "step_id": step.step_id,
                    "kind": step.kind,
                    "summary": "the hosts the task needs, held against the frame",
                },
            )
        refused: str | None = None
        tool_refused = outside_frame("shell.sandboxed", self.frame) and self.fault != "W-07"
        for host in hosts:
            call: Json = {
                "type": "tool.called",
                "step_id": step.step_id,
                "tool": "shell.sandboxed",
                "host": host,
                "arguments_digest": sha256(host.encode()),
            }
            if tool_refused:
                call["refused"] = True
                call["reason"] = "shell.sandboxed is outside the frame's allowed_tools"
                refused = refused or "shell.sandboxed"
            elif host_outside_frame(host, self.frame) and self.fault != "W-13":
                call["refused"] = True
                call["reason"] = f"{host} is not in the frame's allowed_hosts"
                refused = refused or host
            with self.a.lock:
                self.worker._emit(self.a, call)
        self.last_step_id = step.step_id
        self._close_step(step, "refused" if refused else "hosts")
        if refused is not None:
            self.worker._finish(
                self.a,
                "failed",
                reason=f"the task needs {refused!r}, which the frame does not allow",
            )
            return False
        if self.fault != "W-14" and (halt := self._over_ceiling()) is not None:
            self._finish_stopped(halt[1], limit=halt[0])
            return False
        return True

    # -- the agent --

    def _sandbox(self) -> str:
        """The agent's sandbox, chosen by the frame: writable only when the frame allows a
        capability that changes the workspace. `--sandbox none` leaves isolation to the unit
        the worker runs in, for an agent whose own sandbox cannot work there."""
        if self.worker.options.sandbox == "none":
            return "danger-full-access"
        allowed = set(self.frame.get("allowed_tools", []))
        if self.fault == "W-07" or allowed & WRITING:
            return "workspace-write"
        return "read-only"

    def _agent_arguments(self) -> list[str]:
        sandbox = self._sandbox()
        arguments = [
            *self.worker.agent_command,
            "exec",
            "--json",
            "--sandbox",
            sandbox,
            "--skip-git-repo-check",
        ]
        if self.model:
            arguments += ["--model", self.model]
        if sandbox == "workspace-write" and self.frame.get("allowed_hosts"):
            # The frame allows hosts: the sandbox lets commands reach the network, and the
            # unit's egress allowlist is the wall around which hosts.
            arguments += ["--config", "sandbox_workspace_write.network_access=true"]
        resuming = bool(self.a.session_id)
        if resuming:
            arguments += ["resume", self.a.session_id]
        arguments.append(self._prompt(resuming))
        return arguments

    def _prompt(self, resuming: bool) -> str:
        task = self.body["task"]
        lines = [
            "You are an execution unit of an orchestrator. Work in the current directory only.",
            "Do not ask questions; decide and proceed. Do not commit, push or use git.",
            "When the task is done, answer with a short summary of what you changed.",
            "",
            f"Goal: {task['goal']}",
        ]
        acceptance = task.get("acceptance") or []
        if acceptance:
            lines += ["Acceptance:", *(f"- {a}" for a in acceptance)]
        inputs = {k: v for k, v in (task.get("inputs") or {}).items() if k != "hosts"}
        if inputs:
            lines += ["Inputs (JSON):", json.dumps(inputs, indent=2)]
        if resuming:
            lines.insert(0, "Continue the task from where you stopped; do not redo what is done.")
        return "\n".join(lines)

    def _agent_environment(self) -> dict[str, str]:
        keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM")
        proxies = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy")
        env = {k: os.environ[k] for k in (*keep, *proxies) if k in os.environ}
        for name in self.worker.options.agent_env:
            if name in os.environ:
                env[name] = os.environ[name]
        # The agent's home holds its sessions — and, in `session` mode, its login file — under
        # this worker's state, so that a thread outlives a job and nothing of the machine's
        # own login is used.
        env["CODEX_HOME"] = str(self.worker.agent_home)
        env["CI"] = "1"
        if self.worker.auth == "api-key":
            # The credential travels under the assignment's name and reaches the agent under
            # the variable it reads; nothing else of this worker's environment does.
            env[AUTH_VARIABLE["api-key"]] = self.worker.credential_value()
        return env

    def _run_agent(self) -> None:
        a = self.a
        if a.session_id:
            self.session_file = self._find_session(a.session_id)
            if self.session_file is not None:
                self.baseline = self._session_total()[0]
                self.attributed = self.baseline
        arguments = self._agent_arguments()
        log(f"assignment {a.id}: starting the agent ({len(arguments)} arguments)")
        try:
            process = subprocess.Popen(  # noqa: S603 — the configured agent, fixed arguments
                arguments,
                cwd=self.workspace,
                env=self._agent_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            self.worker._finish(a, "failed", reason=f"the agent could not be started: {error}")
            return
        with a.lock:
            a.agent = process
        stderr_lines: list[str] = []
        reader = threading.Thread(
            target=lambda: stderr_lines.extend(process.stderr or []), daemon=True
        )
        reader.start()
        watchdog = threading.Thread(target=self._watch_stop, args=(process,), daemon=True)
        watchdog.start()
        ended_by: str | None = None
        for line in process.stdout or []:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            ended_by = self._on_agent_event(event, process)
            if ended_by is not None:
                break
        try:
            process.wait(timeout=AGENT_EXIT_GRACE)
        except subprocess.TimeoutExpired:
            _end(process, force=True)
            process.wait()
        reader.join(timeout=2)
        self._conclude(process.returncode, ended_by, "".join(stderr_lines))

    def _watch_stop(self, process: subprocess.Popen[str]) -> None:
        """A stop lands at the next boundary; a step that takes longer than the ceiling is
        ended anyway (contracts/worker/v1 §6)."""
        a = self.a
        with a.lock:
            while not a.stop_requested and a.status != "finished" and process.poll() is None:
                a.changed.wait(timeout=0.5)
            if a.status == "finished" or process.poll() is not None:
                return
        deadline = time.monotonic() + a.stop_ceiling
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if process.poll() is None:
            log(f"assignment {a.id}: the running step exceeded the ceiling; ending the agent")
            _end(process, force=True)

    # -- the agent's session file --

    def _find_session(self, thread_id: str) -> Path | None:
        sessions = self.worker.agent_home / "sessions"
        if not sessions.is_dir():
            return None
        found = sorted(sessions.rglob(f"rollout-*{thread_id}.jsonl"))
        return found[-1] if found else None

    def _session_total(self) -> tuple[Tokens, str | None]:
        """The running total of tokens the agent's session file shows — the last count it
        wrote — and the model it last named. Zero when there is no file or no count yet."""
        if self.session_file is None and self.a.session_id:
            self.session_file = self._find_session(self.a.session_id)
        total, model = Tokens(), None
        if self.session_file is None:
            return total, model
        try:
            lines = self.session_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return total, model
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            payload = entry.get("payload") if isinstance(entry, dict) else None
            if not isinstance(payload, dict):
                continue
            if entry.get("type") == "turn_context" and isinstance(payload.get("model"), str):
                model = payload["model"]
            if entry.get("type") != "event_msg" or payload.get("type") != "token_count":
                continue
            usage = (payload.get("info") or {}).get("total_token_usage")
            if isinstance(usage, dict):
                total = _tokens_of(usage)
        return total, model

    def _take_tokens(self) -> Tokens:
        """What the session file shows beyond what earlier steps took: the tokens of the model
        responses since the last step, the one that started this step included."""
        total, model = self._session_total()
        if model:
            self.model = model
        taken = total.minus(self.attributed)
        if total.input >= self.attributed.input:
            self.attributed = total
        return taken

    # -- the agent's stream --

    def _on_agent_event(self, event: Json, process: subprocess.Popen[str]) -> str | None:
        """One line of the agent's stream. Returns why the assignment ends now, or None."""
        kind = event.get("type")
        if kind == "thread.started":
            thread = event.get("thread_id")
            if isinstance(thread, str) and thread and thread != self.a.session_id:
                self.a.session_id = thread
                self.session_file = None
            return None
        if kind == "item.started":
            item = event.get("item") or {}
            if item.get("type") == "command_execution":
                return self._begin(item, process)
            return None
        if kind == "item.completed":
            return self._on_completed(event.get("item") or {}, process)
        if kind == "turn.completed":
            self.turn = event
            return "result"
        if kind == "turn.failed":
            self.failure = str((event.get("error") or {}).get("message") or "the turn failed")
            return "failed"
        if kind == "error":
            message = str(event.get("message") or "")
            if WINDOW.search(message):
                log(f"assignment {self.a.id}: the agent reports its window as exhausted")
                _end(process)
                return "window"
            self.failure = message or self.failure
        return None

    def _on_completed(self, item: Json, process: subprocess.Popen[str]) -> str | None:
        item_type = item.get("type")
        if item_type == "agent_message":
            if isinstance(item.get("text"), str):
                self.last_text = item["text"]
            return None
        if item_type in ("reasoning", "todo_list", "error"):
            return None
        step = self.current
        if step is None or step.item_id != item.get("id"):
            # An item that acts and was not announced as started — a change to files, a call
            # of a tool: it starts and completes at once.
            if (ended := self._begin(item, process)) is not None:
                return ended
            step = self.current
            if step is None:
                return None
        self.current = None
        self._close_step(step, "done")
        if self.fault == "W-10" and step.index == self.a.step_index + 1:
            _end(process)  # the fault: the limits were never checked, and now it is too late
            self.worker._finish(self.a, "failed", reason="limits exceeded after starting")
            return "failed-fault"
        if self.a.stop_requested:
            log(f"assignment {self.a.id}: stop requested; the boundary is here")
            _end(process)
            return "stopped"
        if self.fault != "W-14" and (halt := self._over_ceiling()) is not None:
            log(f"assignment {self.a.id}: a limit is reached; the boundary is here")
            self.halted = halt
            _end(process)
            return "limit"
        return None

    def _begin(self, item: Json, process: subprocess.Popen[str]) -> str | None:
        """An item that acts: a step starts, its call is held against the frame, and a call
        outside it ends the assignment."""
        tool, capability, arguments = self._call_of(item)
        self.index += 1
        step = Step(
            index=self.index,
            step_id=f"step-{self.index}",
            tool=tool,
            capability=capability,
            kind=STEP_KIND.get(capability, "shell" if tool == "command" else "tool"),
            tokens=self._take_tokens(),
            began=time.monotonic(),
            item_id=str(item.get("id") or ""),
        )
        summary = f"{tool}: {_summary_of(item)}"
        with self.a.lock:
            self.worker._emit(
                self.a,
                {
                    "type": "step.started",
                    "step_id": step.step_id,
                    "kind": step.kind,
                    "summary": summary[:200],
                },
            )
        digest = (
            json.dumps(arguments, sort_keys=True) if self.fault == "W-09" else digest_of(arguments)
        )
        call: Json = {
            "type": "tool.called",
            "step_id": step.step_id,
            "tool": capability,
            "arguments_digest": digest,
        }
        if outside_frame(capability, self.frame) and self.fault != "W-07":
            step.refused = True
            call["refused"] = True
            call["reason"] = f"{capability} is outside the frame's allowed_tools"
        with self.a.lock:
            self.worker._emit(self.a, call)
            if self.fault == "W-08-event":
                self.worker._emit(
                    self.a,
                    {
                        "type": "step.progress",
                        "step_id": step.step_id,
                        "message": f"using {self.worker.credential_value()}",  # the fault
                    },
                )
        self.current = step
        self.last_step_id = step.step_id
        if step.refused:
            # The agent asks no permission per call: the call is seen when it appears. The
            # agent is ended, and whatever the call left in the workspace is reset to the last
            # boundary, so that nothing outside the frame survives it.
            _end(process, force=True)
            self._restore()
            self._close_step(step, "refused")
            self.worker._finish(
                self.a,
                "failed",
                reason=f"the agent called {capability}, which the frame does not allow",
            )
            return "refused"
        return None

    def _call_of(self, item: Json) -> tuple[str, str, Json]:
        """The item as a call: its tool, the capability it uses, and its arguments."""
        item_type = item.get("type")
        if item_type == "command_execution":
            command = str(item.get("command") or "")
            return "command", self._capability_of_command(command), {"command": command}
        if item_type == "file_change":
            changes = [
                {"path": str(c.get("path")), "kind": str(c.get("kind"))}
                for c in item.get("changes") or []
                if isinstance(c, dict)
            ]
            return "file_change", "code.edit", {"changes": changes}
        if item_type == "mcp_tool_call":
            name = f"{item.get('server')}.{item.get('tool')}"
            return "mcp_tool_call", f"tool.{name}".lower(), {"arguments": item.get("arguments")}
        if item_type == "web_search":
            return "web_search", "web.search", {"query": item.get("query")}
        return str(item_type), f"tool.{item_type}", {}

    def _capability_of_command(self, command: str) -> str:
        """A command is `code.read` when it only reads, `code.test` when it runs tests and the
        frame allows that, and `shell.sandboxed` otherwise."""
        inner = _unwrap(command)
        allowed = set(self.frame.get("allowed_tools", []))
        if TEST_COMMAND.search(inner) and "code.test" in allowed:
            return "code.test"
        if _only_reads(inner):
            return "code.read"
        return "shell.sandboxed"

    def _restore(self) -> None:
        self._git(["git", "reset", "--quiet", "--hard", "HEAD"], check=False)
        self._git(["git", "clean", "--quiet", "-fd"], check=False)

    def _over_ceiling(self) -> tuple[str, str] | None:
        """The limits are the worker's hard ceiling (W-14). This worker cannot know what the
        agent's next item will use, so it holds the running total itself against each limit
        at every boundary: reached, and nothing more starts. What it can hold per step is
        tokens and quota; the agent reports no money. The limit kind and the reason, or
        None."""
        limits = self.body["limits"]
        bounds: list[tuple[str, str, float]] = [
            ("tokens", f"tokens_{d}", float(limits["tokens"][d]))
            for d in ("in", "out")
            if d in (limits.get("tokens") or {})
        ]
        if "quota" in limits and self.worker.auth == "session":
            bounds.append(("quota", "quota_units", float(limits["quota"]["units"])))
        for kind, quantity, ceiling in bounds:
            if self.used[quantity] >= ceiling:
                return kind, (
                    f"the running total of {self.used[quantity]:g} {quantity} has reached the "
                    f"limit of {ceiling:g}; halted at the boundary of {self.last_step_id}"
                )
        return None

    def _consumption(self, step: Step) -> Json:
        tokens = step.tokens
        consumption: Json = {
            "type": "consumption.reported",
            "step_id": step.step_id,
            "tokens_in": tokens.input,
            "tokens_out": tokens.output,
        }
        if self.model and (tokens.input or tokens.output):
            kinds = {
                "input": max(0, tokens.input - tokens.cached - tokens.cache_write),
                "cache_read": tokens.cached,
                "cache_write": tokens.cache_write,
                "output": tokens.output,
            }
            consumption["tokens_by_model"] = {self.model: kinds}
        if self.worker.auth == "session":
            consumption["quota_units"] = 1
        return consumption

    def _close_step(self, step: Step, how: str) -> None:
        """The boundary after a completed item: the workspace committed, the change an
        artifact, the consumption reported, the checkpoint written, the boundary emitted."""
        a = self.a
        commit: str | None = None
        if how == "done":
            commit = self._commit_change(step)
        consumption = self._consumption(step)
        for quantity in self.used:
            self.used[quantity] += float(consumption.get(quantity, 0))
        with a.lock:
            if self.fault == "W-04":
                self.deferred.append(consumption)
            else:
                self.worker._emit(a, consumption)
            if self.fault == "W-08-log":
                log(f"credential {self.worker.credential_name}={self.worker.credential_value()}")
            skip_boundary = self.fault == "W-06" and a.stop_requested
            checkpoint = self.worker._write_checkpoint(a, step.index, commit)
            if self.fault != "W-05" and not skip_boundary:
                self.worker._emit(
                    a,
                    {
                        "type": "step.boundary",
                        "step_id": step.step_id,
                        "checkpoint_ref": checkpoint,
                    },
                )
            if not skip_boundary:
                self.last_checkpoint = checkpoint

    def _changeset(self) -> str:
        """Every file the assignment changed since the baseline, with its full content, as one
        JSON document: what a connector needs to put the change on a branch without a
        repository of its own (`repository.branches.create`). Text as text, anything else as
        base64; a deleted file by path. Renames count as a deletion and an addition. A file
        the index records as executable carries `executable: true` (DEC-0020, issue #28)."""
        base = self._git(["git", "rev-parse", BASELINE_TAG], check=False).stdout.strip()
        listed = self._git(
            ["git", "diff", "--name-status", "--no-renames", f"{BASELINE_TAG}..HEAD"], check=False
        ).stdout
        executable = self._executable_paths()
        files: list[Json] = []
        deleted: list[str] = []
        for line in listed.splitlines():
            status, _, path = line.partition("\t")
            if not path:
                continue
            if status.startswith("D"):
                deleted.append(path)
                continue
            raw = (self.workspace / path).read_bytes()
            try:
                entry: Json = {"path": path, "content": raw.decode("utf-8"), "encoding": "utf-8"}
            except UnicodeDecodeError:
                entry = {
                    "path": path,
                    "content": base64.b64encode(raw).decode(),
                    "encoding": "base64",
                }
            if path in executable:
                entry["executable"] = True
            files.append(entry)
        return json.dumps({"base": base, "files": files, "deleted": deleted}, ensure_ascii=False)

    def _executable_paths(self) -> set[str]:
        staged = self._git(["git", "ls-files", "--stage"], check=False).stdout
        found: set[str] = set()
        for line in staged.splitlines():
            meta, _, path = line.partition("\t")
            if path and meta.split(" ", 1)[0] == "100755":
                found.add(path)
        return found

    def _commit_change(self, step: Step) -> str | None:
        """What the agent changed in this step, committed and announced as a patch."""
        status = self._git(["git", "status", "--porcelain"], check=False).stdout
        if not status.strip():
            return self._git(["git", "rev-parse", "HEAD"], check=False).stdout.strip() or None
        self._git(["git", "add", "-A"])
        self._git(["git", "commit", "--quiet", "-m", f"taktus: {step.step_id} {step.tool}"])
        commit = self._git(["git", "rev-parse", "HEAD"], check=False).stdout.strip()
        patch = self._git(["git", "show", "--format=", "HEAD"], check=False).stdout.encode()
        if self.fault == "W-08-artifact":
            patch += f"\n{self.worker.credential_name}={self.worker.credential_value()}\n".encode()
        produced = Produced(f"change-{step.index}", "patch", "text/x-diff", patch)
        with self.a.lock:
            self.a.produced.append(produced)
            self.worker._emit(self.a, _artifact_event(self.a, produced, step.step_id))
        return commit or None

    # -- the end --

    def _conclude(self, returncode: int | None, ended_by: str | None, stderr: str) -> None:
        a = self.a
        if a.status == "finished":
            return
        if ended_by == "stopped":
            self._finish_stopped("stop requested; the assignment ended at the boundary")
            return
        if ended_by == "limit" and self.halted is not None:
            self._finish_stopped(self.halted[1], limit=self.halted[0])
            return
        if ended_by == "window":
            self._finish_stopped(
                "the agent's subscription window is exhausted; blocked, not failed"
            )
            return
        if self.current is not None:
            # The agent ended inside a step — killed at the ceiling, or gone on its own. What it
            # left in the workspace is the boundary it reached.
            self._close_step(self.current, "done")
            self.current = None
        if ended_by == "result":
            self._finish_succeeded()
            return
        cause = self.failure or stderr.strip()[-400:] or f"the agent exited with {returncode}"
        if WINDOW.search(cause):
            self._finish_stopped(
                "the agent's subscription window is exhausted; blocked, not failed"
            )
            return
        if AUTH_FAILURE.search(cause):
            self._finish_stopped(f"authentication failed or expired: {cause[:200]}")
            return
        self.worker._finish(a, "failed", reason=cause[:400])

    def _finish_stopped(self, why: str, *, limit: str | None = None) -> None:
        if self.last_checkpoint is None:
            self.worker._finish(self.a, "failed", reason=f"{why}; no boundary was reached")
            return
        self.worker._finish(
            self.a, "stopped", checkpoint_ref=self.last_checkpoint, reason=why, limit=limit
        )

    def _settlement(self) -> Tokens:
        """The report step's tokens: the session file's remainder, and whatever the agent's
        own total for its turn shows beyond everything reported — so that the sum over the
        steps is never less than what the agent says it used."""
        remainder = self._take_tokens()
        usage = (self.turn or {}).get("usage")
        if not isinstance(usage, dict):
            return remainder
        turn = _tokens_of(usage)
        reported = self.attributed.minus(self.baseline)
        return remainder.plus(turn.minus(reported))

    def _finish_succeeded(self) -> None:
        a = self.a
        self.index += 1
        step = Step(
            index=self.index,
            step_id=f"step-{self.index}",
            tool="report",
            capability="code.read",
            kind="report",
            tokens=self._settlement(),
            began=time.monotonic(),
        )
        with a.lock:
            self.worker._emit(
                a,
                {
                    "type": "step.started",
                    "step_id": step.step_id,
                    "kind": "report",
                    "summary": "the agent's summary of what it did",
                },
            )
        summary = Produced("summary", "report", "text/plain", self.last_text.encode())
        if not any(p.artifact_id == "summary" for p in a.inherited):
            with a.lock:
                a.produced.append(summary)
                self.worker._emit(a, _artifact_event(a, summary, step.step_id))
        changeset = Produced(
            "changeset", "changeset", "application/json", self._changeset().encode()
        )
        if not any(p.artifact_id == "changeset" for p in a.inherited):
            with a.lock:
                a.produced.append(changeset)
                self.worker._emit(a, _artifact_event(a, changeset, step.step_id))
        self._close_step(step, "report")
        with a.lock:
            for consumption in self.deferred:
                self.worker._emit(a, consumption)
        if not self._after():
            return
        self.worker._finish(
            a, "succeeded", summary=f"{self.index - a.step_index} step(s) completed"
        )

    def _after(self) -> bool:
        """The task's command after the work (contracts/worker/v1 §3, W-18), as the last step:
        run in the workspace as the agent left it, and its standard output published as the
        artifact the task names. The command is not the agent's: no model is involved. False
        when it failed the assignment."""
        a = self.a
        after = self.body["task"].get("after")
        if not isinstance(after, dict) or self.fault == "W-18":
            return True
        named = str(after["artifact"])
        if any(p.artifact_id == named for p in a.inherited):
            return True
        self.index += 1
        step = Step(
            index=self.index,
            step_id=f"step-{self.index}",
            tool="after",
            capability="shell.sandboxed",
            kind="shell",
            tokens=Tokens(),
            began=time.monotonic(),
        )
        with a.lock:
            self.worker._emit(
                a,
                {
                    "type": "step.started",
                    "step_id": step.step_id,
                    "kind": step.kind,
                    "summary": "the command after the work",
                },
            )
        output, failure = run_after(tuple(str(p) for p in after["command"]), self.workspace)
        if failure is None:
            produced = Produced(named, "output", "text/plain", output)
            with a.lock:
                a.produced.append(produced)
                self.worker._emit(a, _artifact_event(a, produced, step.step_id))
        self.last_step_id = step.step_id
        self._close_step(step, "after")
        if failure is not None:
            self.worker._finish(a, "failed", reason=failure)
            return False
        return True


# --- helpers ------------------------------------------------------------------------------------


def _end(process: subprocess.Popen[str], *, force: bool = False) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def _tokens_of(usage: Json) -> Tokens:
    def count(name: str) -> int:
        value = usage.get(name)
        return int(value) if isinstance(value, int | float) else 0

    return Tokens(
        count("input_tokens"),
        count("cached_input_tokens"),
        count("cache_write_input_tokens"),
        count("output_tokens"),
    )


def _unwrap(command: str) -> str:
    """The script of a command the agent runs through a shell (`bash -lc '…'`), or the
    command itself."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return command
    if len(argv) >= 3 and Path(argv[0]).name in SHELLS and argv[1] in ("-c", "-lc"):
        return argv[2]
    return command


def _only_reads(script: str) -> bool:
    if not script.strip() or WRITES.search(script):
        return False
    for part in re.split(r"&&|\|\||[|;\n]", script):
        words = part.split()
        if not words:
            continue
        program = Path(words[0]).name
        if program == "sed" and "-n" in words[1:] and not any(w.startswith("-i") for w in words):
            continue
        if program not in READING:
            return False
    return True


def run_after(argv: tuple[str, ...], workspace: Path) -> tuple[bytes, str | None]:
    """Run the task's command after the work in the workspace: a program and its arguments,
    without a shell, with no credential in its environment. Its standard output, and why it
    failed or None."""
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
    environment = {k: os.environ[k] for k in keep if k in os.environ}
    try:
        completed = subprocess.run(  # noqa: S603 — the task's own command, by design
            list(argv),
            cwd=workspace,
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
        tail = completed.stderr.decode(errors="replace").strip()[-200:]
        return completed.stdout, (
            f"the command after the work exited with {completed.returncode}"
            + (f": {tail}" if tail else "")
        )
    return completed.stdout, None


def _artifact_event(assignment: Assignment, produced: Produced, step_id: str | None) -> Json:
    event: Json = {"type": "artifact.produced", **produced.describe(assignment.id)}
    event["artifact_id"] = event.pop("id")
    if step_id is not None:
        event["step_id"] = step_id
    return event


def _summary_of(item: Json) -> str:
    if isinstance(item.get("command"), str):
        return _unwrap(item["command"])[:120]
    changes = item.get("changes")
    if isinstance(changes, list):
        return ", ".join(str(c.get("path")) for c in changes if isinstance(c, dict))[:120]
    return "call"


def outside_frame(tool: str, frame: Json) -> bool:
    return tool not in frame.get("allowed_tools", [])


def host_outside_frame(host: str, frame: Json) -> bool:
    return host not in (frame.get("allowed_hosts") or [])


def hosts_of(task: Json) -> list[str]:
    hosts = task.get("inputs", {}).get("hosts")
    if isinstance(hosts, list) and all(isinstance(h, str) for h in hosts):
        return list(dict.fromkeys(hosts))
    return []


def validate_assignment(body: Any) -> str | None:
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
            if running < MAX_CONCURRENT:
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
    # The launch convention of the execution port, as defaults; the options override them.
    port = int(os.environ.get("TAKTUS_UNIT_PORT") or 9000)
    state_dir = os.environ.get("TAKTUS_UNIT_STATE_DIR") or None
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument("--state-dir", default=state_dir, help="checkpoints, workspaces, sessions")
    parser.add_argument(
        "--agent",
        default=os.environ.get("CODING_AGENT_COMMAND") or "codex",
        help="the agent's command line (CODING_AGENT_COMMAND); the gate uses fake_agent.py",
    )
    parser.add_argument(
        "--auth",
        choices=sorted(AUTH_VARIABLE),
        default=os.environ.get("CODING_AGENT_AUTH") or None,
        help="how the agent authenticates (CODING_AGENT_AUTH): api-key or session; required",
    )
    parser.add_argument(
        "--credential",
        default=os.environ.get("CODING_AGENT_CREDENTIAL") or None,
        help="the name the assignment references the credential by, and the variable the value "
        "arrives under (default CODING_AGENT_API_KEY or CODING_AGENT_SESSION)",
    )
    parser.add_argument("--model", default=os.environ.get("CODING_AGENT_MODEL") or None)
    parser.add_argument(
        "--sandbox",
        choices=["frame", "none"],
        default=os.environ.get("CODING_AGENT_SANDBOX") or "frame",
        help="frame: the agent's own sandbox, chosen by the frame (default); none: no sandbox "
        "of the agent's, where the unit the worker runs in is the only isolation "
        "(CODING_AGENT_SANDBOX)",
    )
    parser.add_argument(
        "--agent-env",
        default=os.environ.get("CODING_AGENT_ENV") or "",
        help="names of variables of this worker's environment passed on to the agent, comma "
        "separated (CODING_AGENT_ENV); the credential needs no entry here",
    )
    parser.add_argument("--currency", default="usd", help="the currency limits are given in")
    parser.add_argument("--estimate-tokens-in", type=int, default=60000)
    parser.add_argument("--estimate-tokens-out", type=int, default=6000)
    parser.add_argument("--estimate-currency", type=float, default=1.0)
    parser.add_argument("--estimate-steps", type=int, default=12)
    parser.add_argument("--estimate-wall-seconds", type=int, default=600)
    parser.add_argument("--fault", choices=sorted(FAULTS), help="violate exactly one check")
    parser.add_argument("--list-faults", action="store_true", help="print the faults and exit")
    args = parser.parse_args(argv)
    if args.state_dir is None:
        args.state_dir = str(Path.home() / ".cache" / "taktus-second-coding-worker")
    args.agent_env = [name.strip() for name in args.agent_env.split(",") if name.strip()]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list_faults:
        for name, description in FAULTS.items():
            print(f"{name}\t{check_of(name)}\t{description}")
        return 0
    if args.auth is None:
        sys.stderr.write(
            "second-coding-worker: --auth (or CODING_AGENT_AUTH) is required: api-key or "
            "session. Neither is assumed.\n"
        )
        return 2
    if shutil.which("git") is None:
        sys.stderr.write("second-coding-worker: git is not on the path; the workspace needs it\n")
        return 2
    Handler.worker = Worker(args)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    fault = f", fault {args.fault}" if args.fault else ""
    log(
        f"listening on http://{args.host}:{server.server_port} auth {args.auth} credential "
        f"{Handler.worker.credential_name}{fault}"
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
