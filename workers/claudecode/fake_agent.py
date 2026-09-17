#!/usr/bin/env python3
"""A stand-in for the coding agent's command line, for the conformance gate.

It takes the same options the worker gives the real agent (`-p`, `--output-format stream-json`,
`--tools`, `--allowedTools`, `--session-id`, `--resume`, `--max-turns`, `--model`,
`--permission-mode`), reads the same authentication variables, and writes the same stream: an
`init` line with the session id, `assistant` lines with `tool_use` blocks and `usage`, `user`
lines with the `tool_result`, and a final `result` line with `total_cost_usd` and `num_turns`.
It really does what its tool calls say — writes and edits files, runs shell commands — so that
the worker's boundaries and patches are real, and it keeps its session under
`CLAUDE_CONFIG_DIR`, so that `--resume` continues where it stopped.

What it does not do is think: the plan is fixed. That is the point — the gate proves the
worker's mechanics (boundaries, consumption, refusal, stop, resume, authentication), not the
agent's judgement. Two variables make it misbehave on purpose, so that the worker can be shown
to handle it: `FAKE_AGENT_EXPIRE_AFTER=N` ends the run with an authentication error after N
tool results, as an expired subscription token does; `FAKE_AGENT_WINDOW_AFTER=N` reports the
subscription window as exhausted after N tool results.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

type Json = dict[str, Any]

DENIED = (
    "Permission to use {tool} has been denied because Claude Code is running in don't ask mode."
)

# The fixed plan: what a real agent might do for a small task, one tool call per turn.
PLAN: list[tuple[str, Json]] = [
    ("Glob", {"pattern": "**/*"}),
    ("Write", {"file_path": "notes/plan.md", "content": "# Plan\n\n1. write hello\n2. check\n"}),
    ("Bash", {"command": "printf 'hello\\n' > hello.txt"}),
    ("Read", {"file_path": "hello.txt"}),
    ("Edit", {"file_path": "hello.txt", "old_string": "hello", "new_string": "hello, world"}),
    ("Bash", {"command": "pytest -q 2>/dev/null || printf 'checked\\n' > checked.txt"}),
]
FINAL = "Wrote notes/plan.md and hello.txt, edited the greeting, and ran the check."


def emit(line: Json) -> None:
    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def usage(n: int) -> Json:
    return {
        "input_tokens": 3,
        "cache_creation_input_tokens": 1000 + 100 * n,
        "cache_read_input_tokens": 5000 * n,
        "output_tokens": 40 + n,
    }


def perform(tool: str, arguments: Json) -> tuple[str, bool]:
    """Do what the call says, in the current directory. The text of the result, and whether it
    is an error."""
    if tool == "Glob":
        found = sorted(str(p) for p in Path().rglob("*") if ".git" not in p.parts)
        return "\n".join(found) or "No files found", False
    if tool == "Read":
        path = Path(arguments["file_path"])
        return (path.read_text() if path.is_file() else "File does not exist."), not path.is_file()
    if tool == "Write":
        path = Path(arguments["file_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments["content"])
        return f"File created successfully at: {path}", False
    if tool == "Edit":
        path = Path(arguments["file_path"])
        text = path.read_text()
        if arguments["old_string"] not in text:
            return "String to replace not found in file.", True
        path.write_text(text.replace(arguments["old_string"], arguments["new_string"], 1))
        return f"The file {path} has been updated.", False
    if tool == "Bash":
        completed = subprocess.run(  # noqa: S602 — the fake runs what its fixed plan says
            arguments["command"], shell=True, capture_output=True, text=True, check=False
        )
        return completed.stdout + completed.stderr, completed.returncode != 0
    if tool == "WebFetch":
        return "fetched", False
    return f"unknown tool {tool}", True


def session_path(session_id: str) -> Path:
    directory = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{session_id}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-p", "--print", dest="prompt", default="")
    parser.add_argument("--output-format", default="text")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--permission-mode", default="default")
    parser.add_argument("--tools", default="default")
    parser.add_argument("--allowedTools", "--allowed-tools", default="")
    parser.add_argument("--disallowedTools", "--disallowed-tools", default="")
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)

    session_id = args.resume or args.session_id or str(uuid.uuid4())
    emit({"type": "system", "subtype": "init", "session_id": session_id, "tools": list(dict(PLAN))})
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")):
        emit(
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "result": "Not logged in · Please run /login",
                "session_id": session_id,
                "num_turns": 1,
                "total_cost_usd": 0,
            }
        )
        return 1
    if args.resume and not session_path(session_id).is_file():
        emit(
            {
                "type": "result",
                "subtype": "error",
                "is_error": True,
                "result": f"No conversation found with session ID: {session_id}",
                "session_id": session_id,
                "num_turns": 0,
                "total_cost_usd": 0,
            }
        )
        return 1
    done = 0
    if args.resume:
        done = int(json.loads(session_path(session_id).read_text()).get("done", 0))
    allowed = {t.strip() for t in args.allowedTools.replace(" ", ",").split(",") if t.strip()}
    available = (
        set(dict(PLAN))
        if args.tools == "default"
        else {t.strip() for t in args.tools.split(",") if t.strip()}
    )
    # A resumed run stands for "the operator supplied a working token": it does not expire.
    expire_after = 0 if args.resume else int(os.environ.get("FAKE_AGENT_EXPIRE_AFTER") or 0)
    window_after = int(os.environ.get("FAKE_AGENT_WINDOW_AFTER") or 0)
    pace = float(os.environ.get("FAKE_AGENT_STEP_SECONDS") or 0.15)
    turns = 0
    results = 0
    for n, (tool, arguments) in enumerate(PLAN[done:], done + 1):
        if turns >= args.max_turns:
            break
        turns += 1
        message_id = f"msg_fake{n:04d}"
        call_id = f"toolu_fake{n:04d}"
        # The real agent streams one message in several lines that all carry its usage.
        emit(
            {
                "type": "assistant",
                "message": {
                    "id": message_id,
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"Step {n}: {tool}."}],
                    "usage": usage(n),
                },
                "session_id": session_id,
            }
        )
        emit(
            {
                "type": "assistant",
                "message": {
                    "id": message_id,
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": call_id, "name": tool, "input": arguments}
                    ],
                    "usage": usage(n),
                },
                "session_id": session_id,
            }
        )
        time.sleep(pace)
        if tool not in available or tool not in allowed:
            text, is_error = DENIED.format(tool=tool), True
        else:
            text, is_error = perform(tool, arguments)
        result: Json = {"tool_use_id": call_id, "type": "tool_result", "content": text}
        if is_error:
            result["is_error"] = True
        emit(
            {
                "type": "user",
                "message": {"role": "user", "content": [result]},
                "session_id": session_id,
            }
        )
        results += 1
        session_path(session_id).write_text(json.dumps({"done": n}))
        if expire_after and results >= expire_after:
            emit(
                {
                    "type": "result",
                    "subtype": "error",
                    "is_error": True,
                    "result": "OAuth token expired · Please run /login",
                    "session_id": session_id,
                    "num_turns": turns,
                    "total_cost_usd": 0.01 * turns,
                }
            )
            return 1
        if window_after and results >= window_after:
            emit(
                {
                    "type": "rate_limit_event",
                    "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour"},
                    "session_id": session_id,
                }
            )
            time.sleep(5)  # the real agent would wait for the window; the worker ends it
            return 1
        if is_error and "denied" in text:
            break  # the real agent may try another way; this one gives up
    emit(
        {
            "type": "assistant",
            "message": {
                "id": "msg_fakefinal",
                "role": "assistant",
                "content": [{"type": "text", "text": FINAL}],
                "usage": usage(99),
            },
            "session_id": session_id,
        }
    )
    emit(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": FINAL,
            "session_id": session_id,
            "num_turns": turns + 1,
            "total_cost_usd": round(0.02 * (turns + 1), 4),
            "usage": usage(99),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
