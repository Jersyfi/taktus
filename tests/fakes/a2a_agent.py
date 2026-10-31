"""A reference agent: a small local server of the open agent-to-agent protocol (A2A, ADR-0172).

It is the foreign agent the A2A binding of the worker contract is proven against. It speaks the
protocol's JSON-RPC binding of version 0.3: its agent card at
`GET /.well-known/agent-card.json`, and the methods `message/send`, `tasks/get` and
`tasks/cancel` at `POST /a2a`. It knows nothing of Taktus, of the worker contract, of steps,
limits or boundaries.

A message without a `taskId` opens a task. The task does nothing but keep time: every
`turn_seconds` its status changes, first to `working` once per turn, and after the last turn
to `completed`, with one artifact `report` of a text part naming the goal. A message with the
`taskId` of a task the agent holds is a further message into that task: it is kept, and the
artifact names it.

`ask_input` makes the task stop after its first turn in `input-required`, asking a question,
until a further message arrives; the task then goes on from there. `fail_tasks` makes every
task fail after its first turn. `answer_at_once` makes the agent answer a message with a
message of its own instead of a task, as an agent with nothing to run does.

Every JSON-RPC request carries the agent's token as `Authorization: Bearer <token>`; one
without it is answered 401. The card is public, as the protocol has it. The agent keeps what
it was sent (`received`), so that a test can show what reached it and that nothing reached it
where the frame did not allow it. It keeps no token in anything it records.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

type Json = dict[str, Any]

PROTOCOL = "0.3.0"
TERMINAL = ("completed", "failed", "canceled", "rejected")
QUESTION = "Which audience is the report for?"


def stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def text_of(message: Json) -> str:
    parts = message.get("parts") or []
    return "\n".join(str(p.get("text", "")) for p in parts if p.get("kind") == "text")


@dataclass
class Task:
    id: str
    context_id: str
    goal: str
    turns: int
    fail: bool
    ask: bool
    turned_at: float
    done: int = 0
    waiting: bool = False
    asked: bool = False
    state: str = "submitted"
    note: str = "the task is submitted"
    status_id: str = ""
    status_at: str = field(default_factory=stamp)
    further: list[str] = field(default_factory=list)

    def advance(self, seconds: float) -> None:
        """Move the task on by the time that passed, turn by turn."""
        while self.state not in TERMINAL and not self.waiting:
            if time.monotonic() - self.turned_at < seconds:
                return
            self.turned_at += seconds
            self.done += 1
            if self.fail:
                self.set("failed", "the agent could not draft the report")
            elif self.ask and not self.asked and self.done == 1:
                self.asked = True
                self.waiting = True
                self.set("input-required", QUESTION)
            elif self.done >= self.turns:
                self.set("completed", f"drafted the report in {self.done} turns")
            else:
                self.set("working", f"turn {self.done} of {self.turns}: drafting")

    def set(self, state: str, note: str) -> None:
        self.state = state
        self.note = note
        self.status_id = f"{self.id}-status-{self.done}-{state}-{len(self.further)}"
        self.status_at = stamp()

    def document(self) -> Json:
        status: Json = {
            "state": self.state,
            "timestamp": self.status_at,
            "message": {
                "kind": "message",
                "role": "agent",
                "messageId": self.status_id or f"{self.id}-status-0",
                "taskId": self.id,
                "contextId": self.context_id,
                "parts": [{"kind": "text", "text": self.note}],
            },
        }
        task: Json = {
            "kind": "task",
            "id": self.id,
            "contextId": self.context_id,
            "status": status,
        }
        if self.state == "completed":
            text = f"Report on: {self.goal}"
            if self.further:
                text += "\nAlso considered: " + " | ".join(self.further)
            task["artifacts"] = [
                {
                    "artifactId": "report",
                    "name": "report",
                    "parts": [{"kind": "text", "text": text}],
                }
            ]
        return task


@dataclass
class ReferenceAgent:
    """The agent, in this process: `start()` serves it on a free port of 127.0.0.1."""

    token: str
    turn_seconds: float = 0.3
    turns: int = 3
    fail_tasks: bool = False
    ask_input: bool = False
    answer_at_once: bool = False
    received: list[Json] = field(default_factory=list)
    """Every message that reached the agent, as it arrived."""
    reads: int = 0
    tasks: dict[str, Task] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _server: ThreadingHTTPServer | None = None

    @property
    def host(self) -> str:
        assert self._server is not None, "the agent is not started"
        return f"127.0.0.1:{self._server.server_port}"

    @property
    def url(self) -> str:
        return f"http://{self.host}"

    def start(self, port: int = 0) -> ReferenceAgent:
        agent = self

        class Bound(Handler):
            pass

        Bound.agent = agent
        self._server = ThreadingHTTPServer(("127.0.0.1", port), Bound)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def card(self) -> Json:
        return {
            "protocolVersion": PROTOCOL,
            "name": "reference agent",
            "description": "Drafts a short report on a goal. A stand-in for a foreign agent.",
            "url": f"{self.url}/a2a",
            "preferredTransport": "JSONRPC",
            "version": "1.0.0",
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["text/plain", "application/json"],
            "defaultOutputModes": ["text/plain"],
            "skills": [
                {
                    "id": "draft-report",
                    "name": "draft a report",
                    "description": "drafts a short report on the goal it is given",
                    "tags": ["report"],
                }
            ],
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
            "security": [{"bearer": []}],
        }

    # -- the methods --

    def call(self, method: str, params: Json) -> tuple[Any, Json | None]:
        """The result of one method, or its JSON-RPC error."""
        with self.lock:
            if method == "message/send":
                return self._send(params)
            if method == "tasks/get":
                self.reads += 1
                task = self.tasks.get(str(params.get("id")))
                if task is None:
                    return None, {"code": -32001, "message": "task not found"}
                task.advance(self.turn_seconds)
                return task.document(), None
            if method == "tasks/cancel":
                task = self.tasks.get(str(params.get("id")))
                if task is None:
                    return None, {"code": -32001, "message": "task not found"}
                task.advance(self.turn_seconds)
                if task.state in TERMINAL:
                    return None, {"code": -32002, "message": "task cannot be canceled"}
                task.set("canceled", "the task was canceled")
                return task.document(), None
        return None, {"code": -32601, "message": "method not found"}

    def _send(self, params: Json) -> tuple[Any, Json | None]:
        message = params.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("parts"), list):
            return None, {"code": -32602, "message": "a message with parts is required"}
        self.received.append(json.loads(json.dumps(message)))
        task_id = message.get("taskId")
        if task_id is not None:
            task = self.tasks.get(str(task_id))
            if task is None:
                return None, {"code": -32001, "message": "task not found"}
            task.advance(self.turn_seconds)
            if task.state in TERMINAL:
                return None, {"code": -32004, "message": "the task has ended"}
            task.further.append(text_of(message))
            if task.waiting:
                task.waiting = False
                task.turned_at = time.monotonic()
                task.set("working", "received the answer; drafting on")
            return task.document(), None
        if self.answer_at_once:
            return {
                "kind": "message",
                "role": "agent",
                "messageId": "msg-" + secrets.token_hex(6),
                "parts": [{"kind": "text", "text": f"Answer to: {text_of(message)[:80]}"}],
            }, None
        task = Task(
            id="task-" + secrets.token_hex(6),
            context_id="ctx-" + secrets.token_hex(6),
            goal=text_of(message).split("\n")[0],
            turns=self.turns,
            fail=self.fail_tasks,
            ask=self.ask_input,
            turned_at=time.monotonic(),
        )
        task.status_id = f"{task.id}-status-0"
        self.tasks[task.id] = task
        return task.document(), None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    agent: ReferenceAgent

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _json(self, status: int, body: Json) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/.well-known/agent-card.json":
            self._json(200, self.agent.card())
        else:
            self._json(404, {"title": "no such route", "status": 404})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if self.headers.get("Authorization") != f"Bearer {self.agent.token}":
            self._json(401, {"title": "unauthorised", "status": 401})
            return
        if self.path != "/a2a":
            self._json(404, {"title": "no such route", "status": 404})
            return
        try:
            request = json.loads(raw or b"{}")
        except ValueError:
            self._json(200, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700}})
            return
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            self._json(200, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600}})
            return
        result, error = self.agent.call(str(request.get("method")), request.get("params") or {})
        answer: Json = {"jsonrpc": "2.0", "id": request.get("id")}
        if error is not None:
            answer["error"] = error
        else:
            answer["result"] = result
        self._json(200, answer)
