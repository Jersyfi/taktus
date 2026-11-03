"""A stand-in for a software factory: the generic task API the factory worker speaks (ADR-0157).

A software factory takes a task and returns a finished change. This one does nothing but keep
time. A task posted at `POST /tasks` completes one stage every `stage_seconds`, each costing
`stage_cost` in the factory's currency, and has succeeded once its last stage is done. Its
state is at `GET /tasks/{id}`, its change at `GET /tasks/{id}/change` once it succeeded.

Every request carries the factory's token as `Authorization: Bearer <token>`; one without it is
answered 401. The service keeps what it was sent (`submissions`), so that a test can show what
reached a factory and that a step outside the residency rule sent nothing. It keeps no token
in anything it records.

`fail_tasks` makes every task fail after its first stage, as a factory whose checks reject the
change does. Run as a program, it serves on a port until it is stopped:
`python3 tests/fakes/factory_service.py --port 9300 --token-file token`.
"""

from __future__ import annotations

import argparse
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

type Json = dict[str, Any]

STAGES = (
    ("specify", "wrote the specification of the change"),
    ("implement", "implemented the change"),
    ("review", "reviewed the change and ran the checks"),
)
CHANGE: Json = {
    "base": "0" * 40,
    "files": [{"path": "hello.txt", "content": "hello\n", "encoding": "utf-8"}],
    "deleted": [],
}


@dataclass
class Task:
    id: str
    body: Json
    posted: float
    stages: tuple[tuple[str, str], ...]
    fail: bool


@dataclass
class FakeFactory:
    """The service, in this process: `start()` serves it on a free port of 127.0.0.1."""

    token: str
    stage_seconds: float = 0.3
    stage_cost: float = 0.5
    currency: str = "eur"
    fail_tasks: bool = False
    stages: tuple[tuple[str, str], ...] = STAGES
    submissions: list[Json] = field(default_factory=list)
    reads: int = 0
    tasks: dict[str, Task] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _server: ThreadingHTTPServer | None = None

    @property
    def host(self) -> str:
        assert self._server is not None, "the factory is not started"
        return f"127.0.0.1:{self._server.server_port}"

    @property
    def url(self) -> str:
        return f"http://{self.host}"

    def start(self, port: int = 0) -> FakeFactory:
        factory = self

        class Bound(Handler):
            pass

        Bound.factory = factory
        self._server = ThreadingHTTPServer(("127.0.0.1", port), Bound)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    # -- the API --

    def submit(self, body: Json) -> Json:
        with self.lock:
            task = Task(
                id="tsk_" + secrets.token_hex(6),
                body=body,
                posted=time.monotonic(),
                stages=self.stages[:1] if self.fail_tasks else self.stages,
                fail=self.fail_tasks,
            )
            self.tasks[task.id] = task
            self.submissions.append(body)
        return {"id": task.id}

    def state(self, task: Task) -> Json:
        with self.lock:
            self.reads += 1
        done = min(int((time.monotonic() - task.posted) / self.stage_seconds), len(task.stages))
        finished = done == len(task.stages)
        state: Json = {
            "id": task.id,
            "state": ("failed" if task.fail else "succeeded") if finished else "running",
            "stages": [{"name": n, "summary": s} for n, s in task.stages[:done]],
            "cost": {"amount": round(done * self.stage_cost, 6), "currency": self.currency},
        }
        if finished and not task.fail:
            state["summary"] = f"Implemented: {task.body.get('title', 'the task')}"
        if finished and task.fail:
            state["reason"] = "the factory's review rejected the change"
        return state


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    factory: FakeFactory

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _json(self, status: int, body: Json) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {self.factory.token}":
            return True
        self._json(401, {"title": "unauthorised", "status": 401})
        return False

    def _task(self, task_id: str) -> Task | None:
        task = self.factory.tasks.get(task_id)
        if task is None:
            self._json(404, {"title": "no such task", "status": 404})
        return task

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not self._authorised():
            return
        if self.path != "/tasks":
            self._json(404, {"title": "no such route", "status": 404})
            return
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            self._json(400, {"title": "not JSON", "status": 400})
            return
        if not isinstance(body, dict) or not isinstance(body.get("title"), str):
            self._json(400, {"title": "a task needs a title", "status": 400})
            return
        self._json(201, self.factory.submit(body))

    def do_GET(self) -> None:
        if not self._authorised():
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "tasks":
            if (task := self._task(parts[1])) is not None:
                self._json(200, self.factory.state(task))
        elif len(parts) == 3 and parts[0] == "tasks" and parts[2] == "change":
            if (task := self._task(parts[1])) is not None:
                if self.factory.state(task)["state"] != "succeeded":
                    self._json(409, {"title": "the task has no change yet", "status": 409})
                else:
                    self._json(200, CHANGE)
        else:
            self._json(404, {"title": "no such route", "status": 404})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=9300)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--stage-seconds", type=float, default=0.3)
    parser.add_argument("--stage-cost", type=float, default=0.5)
    args = parser.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    factory = FakeFactory(token, args.stage_seconds, args.stage_cost).start(args.port)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        factory.stop()


if __name__ == "__main__":
    main()
