#!/usr/bin/env python3
"""A stand-in for the second coding agent's command line, for the conformance gate.

It takes the options the worker gives the real agent (`exec --json`, `--sandbox`, `--model`,
`--config`, `--skip-git-repo-check`, `resume <thread>`, the prompt), reads the same
authentication — the variable `CODEX_API_KEY`, or the login file `auth.json` in `CODEX_HOME` —
and writes the same stream, the agent's documented non-interactive output: `thread.started`
with the thread's id, `turn.started`, `item.started` and `item.completed` for every command it
runs, `item.completed` for every change it makes to files and for its closing message, and
`turn.completed` with the turn's usage. Beside the stream it keeps the agent's session file under
`CODEX_HOME/sessions/`, where it writes the running total of tokens after every model response
and before acting on it, as the real agent does. That file is what the worker reads its tokens
per step from.

It really does what its items say — runs commands, writes and changes files — so that the
worker's boundaries and patches are real. Its sandbox is real in the one way the gate needs: a
`read-only` sandbox changes no file. Commands it runs as they are.

What it does not do is think: the plan is fixed. Two variables make it misbehave on purpose:
`FAKE_AGENT_EXPIRE_AFTER=N` fails the turn with an authentication error after N completed
items, as an expired login does; `FAKE_AGENT_WINDOW_AFTER=N` reports the usage limit as reached
after N completed items. Its usage is fixed and overruns the worker's default estimate — about
620 000 input tokens for the whole plan against 60 000 — so that the worker can be shown to halt
when a running total reaches its limit (W-14). `FAKE_AGENT_USAGE_FACTOR` scales every count.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

type Json = dict[str, Any]

# The fixed plan: what a real agent might do for a small task, one item per model response.
PLAN: list[tuple[str, Json]] = [
    ("command", {"command": "ls"}),
    ("add", {"path": "notes/plan.md", "content": "# Plan\n\n1. write hello\n2. check\n"}),
    ("command", {"command": "printf 'hello\\n' > hello.txt"}),
    ("command", {"command": "cat hello.txt"}),
    ("update", {"path": "hello.txt", "old": "hello", "new": "hello, world"}),
    ("command", {"command": "pytest -q 2>/dev/null || printf 'checked\\n' > checked.txt"}),
]
FINAL = "Wrote notes/plan.md and hello.txt, changed the greeting, and ran the check."
MODEL = "fake-coding-model"


def emit(line: Json) -> None:
    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def usage(n: int) -> Json:
    """One model response's tokens. Input counts every input token, the cached ones too."""
    factor = float(os.environ.get("FAKE_AGENT_USAGE_FACTOR") or 1)
    cached = 5000 * n
    counts = {
        "input_tokens": 1003 + 100 * n + cached,
        "cached_input_tokens": cached,
        "cache_write_input_tokens": 0,
        "output_tokens": 40 + n,
        "reasoning_output_tokens": 10,
    }
    return {name: max(0, round(factor * count)) for name, count in counts.items()}


def added(total: Json, more: Json) -> Json:
    return {name: int(total.get(name, 0)) + int(more.get(name, 0)) for name in more}


class Session:
    """The agent's session file: one JSON line per entry, under `CODEX_HOME/sessions/`."""

    def __init__(self, home: Path, thread: str, *, create: bool) -> None:
        directory = home / "sessions" / "2026" / "10" / "10"
        found = sorted((home / "sessions").rglob(f"rollout-*{thread}.jsonl"))
        if found:
            self.path = found[-1]
        elif create:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"rollout-2026-10-10T00-00-00-{thread}.jsonl"
            self.write("session_meta", {"id": thread})
        else:
            raise FileNotFoundError(thread)
        self.total: Json = {}
        self.done = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            payload = entry.get("payload") or {}
            if payload.get("type") == "token_count":
                self.total = payload["info"]["total_token_usage"]
            if entry.get("type") == "fake_progress":
                self.done = int(payload["done"])

    def write(self, kind: str, payload: Json) -> None:
        stamp = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.path.open("a", encoding="utf-8") as handle:
            line = {"timestamp": stamp, "type": kind, "payload": payload}
            handle.write(json.dumps(line, separators=(",", ":")) + "\n")

    def respond(self, n: int) -> Json:
        """One model response: its tokens added to the running total, written before the
        response is acted on."""
        last = usage(n)
        self.total = added(self.total, last)
        info = {"total_token_usage": self.total, "last_token_usage": last}
        self.write("event_msg", {"type": "token_count", "info": info, "rate_limits": None})
        return last


def perform(kind: str, arguments: Json, writable: bool) -> tuple[str, int]:
    """Do what the item says, in the current directory: the output and the exit code."""
    if kind == "command":
        completed = subprocess.run(  # noqa: S602 — the fake runs what its fixed plan says
            arguments["command"], shell=True, capture_output=True, text=True, check=False
        )
        return completed.stdout + completed.stderr, completed.returncode
    if not writable:
        return "the sandbox is read-only", 1
    path = Path(arguments["path"])
    if kind == "add":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments["content"])
        return "", 0
    text = path.read_text() if path.is_file() else ""
    if arguments["old"] not in text:
        return "patch did not apply", 1
    path.write_text(text.replace(arguments["old"], arguments["new"], 1))
    return "", 0


def parse(argv: list[str]) -> Json:
    if not argv or argv[0] != "exec":
        raise SystemExit("fake agent: only `exec` is imitated")
    options: Json = {"sandbox": "read-only", "json": False, "resume": None, "prompt": ""}
    rest = argv[1:]
    i = 0
    while i < len(rest):
        word = rest[i]
        if word == "--json":
            options["json"] = True
        elif word in ("--sandbox", "-s"):
            options["sandbox"] = rest[i + 1]
            i += 1
        elif word in ("--model", "-m", "--config", "-c"):
            i += 1
        elif word == "--skip-git-repo-check":
            pass
        elif word == "resume":
            options["resume"] = rest[i + 1]
            i += 1
        else:
            options["prompt"] = word
        i += 1
    return options


def main(argv: list[str] | None = None) -> int:
    options = parse(sys.argv[1:] if argv is None else argv)
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    logged_in = bool(os.environ.get("CODEX_API_KEY")) or (home / "auth.json").is_file()
    thread = options["resume"] or str(uuid.uuid4())
    if options["resume"]:
        try:
            session = Session(home, thread, create=False)
        except FileNotFoundError:
            emit({"type": "error", "message": f"no rollout found for thread id {thread}"})
            return 1
    else:
        session = Session(home, thread, create=True)
    emit({"type": "thread.started", "thread_id": thread})
    emit({"type": "turn.started"})
    if not logged_in:
        message = "unexpected status 401 Unauthorized: Missing bearer or basic authentication"
        emit({"type": "turn.failed", "error": {"message": message}})
        return 1
    session.write("turn_context", {"model": MODEL, "cwd": str(Path.cwd())})
    writable = options["sandbox"] != "read-only"
    # A resumed run stands for "the operator supplied a working login": it does not expire.
    expire_after = 0 if options["resume"] else int(os.environ.get("FAKE_AGENT_EXPIRE_AFTER") or 0)
    window_after = int(os.environ.get("FAKE_AGENT_WINDOW_AFTER") or 0)
    pace = float(os.environ.get("FAKE_AGENT_STEP_SECONDS") or 0.15)
    turn: Json = {}
    completed = 0
    for n, (kind, arguments) in enumerate(PLAN[session.done :], session.done + 1):
        turn = added(turn, session.respond(n))
        item_id = f"item_{n}"
        if kind == "command":
            command = shlex.join(["bash", "-lc", arguments["command"]])
            item: Json = {
                "id": item_id,
                "type": "command_execution",
                "command": command,
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            }
            emit({"type": "item.started", "item": item})
            time.sleep(pace)
            output, code = perform(kind, arguments, writable)
            item = {
                **item,
                "aggregated_output": output,
                "exit_code": code,
                "status": "completed" if code == 0 else "failed",
            }
        else:
            time.sleep(pace)
            _, code = perform(kind, arguments, writable)
            item = {
                "id": item_id,
                "type": "file_change",
                "changes": [{"path": arguments["path"], "kind": kind}],
                "status": "completed" if code == 0 else "failed",
            }
        emit({"type": "item.completed", "item": item})
        session.write("fake_progress", {"done": n})
        completed += 1
        if expire_after and completed >= expire_after:
            message = "unexpected status 401 Unauthorized: Your access token has expired"
            emit({"type": "turn.failed", "error": {"message": message}})
            return 1
        if window_after and completed >= window_after:
            emit({"type": "error", "message": "You've hit your usage limit. Try again later."})
            time.sleep(5)  # the real agent would wait; the worker ends it
            return 1
    turn = added(turn, session.respond(99))
    emit(
        {
            "type": "item.completed",
            "item": {"id": "item_final", "type": "agent_message", "text": FINAL},
        }
    )
    emit({"type": "turn.completed", "usage": turn})
    return 0


if __name__ == "__main__":
    sys.exit(main())
