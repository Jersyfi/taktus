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

It is offered the tools `--tools` names, as the real agent is, and never calls another: a
step of its plan whose tool it is not offered is left out. A tool it is offered and not
approved (`--allowedTools`) it calls, and is denied.

What it does not do is think: the plan is fixed. That is the point — the gate proves the
worker's mechanics (boundaries, consumption, refusal, stop, resume, authentication), not the
agent's judgement. Three variables make it misbehave on purpose, so that the worker can be shown
to handle it: `FAKE_AGENT_EXPIRE_AFTER=N` ends the run with an authentication error after N
tool results, as an expired subscription token does; `FAKE_AGENT_WINDOW_AFTER=N` reports the
subscription window as exhausted after N tool results; `FAKE_AGENT_HANG_AFTER=N` writes the text
of its next message after N tool results, with the message's usage, and then works on it without
end, so that a stop lands inside a message whose call never comes (#277). `FAKE_AGENT_WRITE`
adds files to the change (`plan()`). `FAKE_AGENT_PARALLEL=1` makes two calls per message, as
the real agent does when it calls tools in parallel: both calls come first, each in a line of
its own, then both results — with `reversed`, the second call's result first.

Its usage is fixed too, and it overruns: about 620 000 input tokens for the whole plan, ten
times the worker's default estimate of 60 000 — the real agent used 1.8 to 4.3 times that
estimate in the first live run. So the worker can be shown to halt when a running total
reaches its limit (W-14). `FAKE_AGENT_USAGE_FACTOR` scales every token count (default 1); a
small factor keeps the run within the estimate.

Every message is streamed in several lines whose usage grows, as the real agent's does: the
first line carries a twentieth of the message's output, the last all of it. The final line
carries the session's total. `FAKE_AGENT_LATE_USAGE=1` keeps every
line at the fraction, so that only the total holds the rest.

Every message names its model, as the real agent's does: `--model`, or `MODEL` below, which the
worker's price table prices. A run that reaches `--max-turns` with its plan unfinished ends as
the real agent's does: a result with the subtype `error_max_turns`, no text, and exit code 1
(#375, #380); its session keeps what it did, so that `--resume` continues after it.
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


def plan() -> list[tuple[str, Json]]:
    """The fixed plan, with one `Write` before the check for every file `FAKE_AGENT_WRITE`
    names — a JSON object of path to content — so that a test can give the change a file of
    its choosing, a record of a register among them. `FAKE_AGENT_FETCH` names a URL the plan
    fetches first, as the real agent fetched a page on the instance (#424)."""
    extra = json.loads(os.environ.get("FAKE_AGENT_WRITE") or "{}")
    writes = [("Write", {"file_path": path, "content": text}) for path, text in extra.items()]
    fetch = os.environ.get("FAKE_AGENT_FETCH")
    fetches = [("WebFetch", {"url": fetch, "prompt": "read it"})] if fetch else []
    return [*fetches, *PLAN[:-1], *writes, PLAN[-1]]


FINAL = "Wrote notes/plan.md and hello.txt, edited the greeting, and ran the check."
MODEL = "claude-haiku-4-5-20251001"
"""The model a message names where `--model` names none: as the real agent names it, dated."""


def emit(line: Json) -> None:
    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def usage(n: int) -> Json:
    factor = float(os.environ.get("FAKE_AGENT_USAGE_FACTOR") or 1)
    counts = {
        "input_tokens": 3,
        "cache_creation_input_tokens": 1000 + 100 * n,
        "cache_read_input_tokens": 5000 * n,
        "output_tokens": 40 + n,
    }
    return {name: max(0, round(factor * count)) for name, count in counts.items()}


def partial(full: Json) -> Json:
    """A message's usage while it is still streamed: its input, a fraction of its output."""
    return {**full, "output_tokens": full["output_tokens"] // 20}


def add(total: Json, used: Json) -> Json:
    return {name: total.get(name, 0) + count for name, count in used.items()}


def message(message_id: str, blocks: list[Json], used: Json, session_id: str) -> Json:
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "model": os.environ.get("FAKE_AGENT_MODEL") or MODEL,
            "role": "assistant",
            "content": blocks,
            "usage": used,
        },
        "session_id": session_id,
    }


def stream(
    message_id: str, text: str, last: Json | list[Json], full: Json, session_id: str
) -> None:
    """One message in a line per block: its text with the usage so far, then each further
    block, the last with all of it — or, with `FAKE_AGENT_LATE_USAGE`, still the usage so
    far. Several tool calls in one message come as several lines, as the real agent's do."""
    late = bool(os.environ.get("FAKE_AGENT_LATE_USAGE"))
    blocks = last if isinstance(last, list) else [last]
    emit(message(message_id, [{"type": "text", "text": text}], partial(full), session_id))
    for i, block in enumerate(blocks, 1):
        final = i == len(blocks) and not late
        emit(message(message_id, [block], full if final else partial(full), session_id))


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


def save_session(session_id: str, done: int) -> None:
    """Replace the session at once, so that an agent ended at any moment leaves a whole one."""
    path = session_path(session_id)
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps({"done": done}))
    os.replace(partial, path)


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
    if args.model:
        os.environ["FAKE_AGENT_MODEL"] = args.model

    session_id = args.resume or args.session_id or str(uuid.uuid4())
    emit(
        {"type": "system", "subtype": "init", "session_id": session_id, "tools": list(dict(plan()))}
    )
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
        set(dict(plan()))
        if args.tools == "default"
        else {t.strip() for t in args.tools.split(",") if t.strip()}
    )
    # A resumed run stands for "the operator supplied a working token": it does not expire.
    expire_after = 0 if args.resume else int(os.environ.get("FAKE_AGENT_EXPIRE_AFTER") or 0)
    window_after = int(os.environ.get("FAKE_AGENT_WINDOW_AFTER") or 0)
    hang_after = int(os.environ.get("FAKE_AGENT_HANG_AFTER") or 0)
    pace = float(os.environ.get("FAKE_AGENT_STEP_SECONDS") or 0.15)
    turns = 0
    results = 0
    total: Json = {}
    # A tool it is not offered is one it does not know: it never calls it.
    remaining = [
        (n, tool, arguments)
        for n, (tool, arguments) in enumerate(plan()[done:], done + 1)
        if tool in available
    ]
    width = 2 if os.environ.get("FAKE_AGENT_PARALLEL") else 1
    finished = done
    denied = False
    while remaining and not denied:
        batch, remaining = remaining[:width], remaining[width:]
        if hang_after and results >= hang_after:
            n = batch[0][0]
            text = {"type": "text", "text": f"Step {n}: thinking."}
            emit(message(f"msg_fake{n:04d}", [text], usage(n), session_id))
            time.sleep(600)  # the worker ends it
            return 1
        if turns >= args.max_turns:
            emit(
                {
                    "type": "result",
                    "subtype": "error_max_turns",
                    "is_error": True,
                    "session_id": session_id,
                    "num_turns": turns,
                    "total_cost_usd": round(0.02 * turns, 4),
                    "usage": total,
                }
            )
            return 1
        turns += 1
        first = batch[0][0]
        calls = [
            {"type": "tool_use", "id": f"toolu_fake{n:04d}", "name": tool, "input": arguments}
            for n, tool, arguments in batch
        ]
        names = " and ".join(tool for _, tool, _ in batch)
        stream(f"msg_fake{first:04d}", f"Step {first}: {names}.", calls, usage(first), session_id)
        total = add(total, usage(first))
        pairs = list(zip(batch, calls, strict=True))
        if os.environ.get("FAKE_AGENT_PARALLEL") == "reversed":
            pairs.reverse()  # the later call finishes first, and its result comes first
        for (n, tool, arguments), call in pairs:
            time.sleep(pace)
            if tool not in allowed:
                text, is_error = DENIED.format(tool=tool), True
            else:
                text, is_error = perform(tool, arguments)
            result: Json = {"tool_use_id": call["id"], "type": "tool_result", "content": text}
            if is_error:
                result["is_error"] = True
            finished = max(finished, n)
            # The session holds the call before its result is streamed: the worker ends the
            # agent at the boundary that result opens, and a session written after it was lost
            # or, cut off mid-write, left empty, so that the resume failed (#389).
            save_session(session_id, finished)
            emit(
                {
                    "type": "user",
                    "message": {"role": "user", "content": [result]},
                    "session_id": session_id,
                }
            )
            results += 1
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
                denied = True  # the real agent may try another way; this one gives up
                break
    stream("msg_fakefinal", "Done.", {"type": "text", "text": FINAL}, usage(99), session_id)
    total = add(total, usage(99))
    emit(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": FINAL,
            "session_id": session_id,
            "num_turns": turns + 1,
            "total_cost_usd": round(0.02 * (turns + 1), 4),
            "usage": total,  # the session's total: every message, each once
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
