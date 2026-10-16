"""Keep `main` green while pull requests merge without catching up (ADR-0096 §5, #391).

Three subcommands, each deciding from files the workflow fetched from the host. The tool itself
never holds a token and never calls the host, so that what it decides is tested against a
stubbed host's answers (`tests/tools/test_ci_watch.py`).

`guard --runs FILE --title TITLE --body-file FILE`
    The last step of the required check on a pull request. FILE is the host's answer for the
    newest runs of `ci` on `main`. The newest completed run decides: when it failed, the pull
    request may merge only if it reverts (its title starts `Revert "` or `revert`) or its
    description names `Mends main: <sha>`. A file that is missing, empty or not the host's
    answer fails the guard: when the host does not answer, nothing merges (fail closed).

`failed-tests --log FILE`
    The tests a failed run names, from its log (`gh run view --log-failed`): every
    `FAILED tests/...` and `ERROR tests/...` of pytest's summary, once each, in order.

`decide --run FILE`
    What follows a finished run of `ci`, FILE being the `workflow_run` event's run. One word:
    - `rerun`: the first attempt failed; it is repeated once.
    - `flake`: a repeat passed where the attempt before it failed; its failing tests go to the
      flake register.
    - `main-red`: a run on `main` failed on its repeat; the issue "main is red" is opened or
      updated.
    - `main-green`: a run on `main` passed at its first attempt; "main is red" is closed.
    - `none`: nothing to do — a cancelled or skipped run, a repeat that failed off `main`.
    A flake on `main` closes "main is red" too; the workflow does that.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MENDS = re.compile(r"^Mends main: [0-9a-f]{7,40}\b", re.MULTILINE)
REVERT = re.compile(r'^(Revert "|revert\b)', re.IGNORECASE)
FAILED_TEST = re.compile(r"\b(?:FAILED|ERROR) (tests/[^\s]+)")


def newest_completed(answer: Any) -> dict[str, Any] | None:
    """The newest completed run in the host's answer, or None when it holds none. Raises
    ValueError when the answer is not the host's list of runs."""
    if not isinstance(answer, dict) or not isinstance(answer.get("workflow_runs"), list):
        raise ValueError("not a list of workflow runs")
    runs = [r for r in answer["workflow_runs"] if isinstance(r, dict)]
    completed = [r for r in runs if r.get("status") == "completed"]
    completed.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return completed[0] if completed else None


def guard(runs_file: Path, title: str, body: str) -> tuple[bool, str]:
    """Whether the pull request may merge, and why."""
    try:
        newest = newest_completed(json.loads(runs_file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        return (
            False,
            f"the host did not say how main stands ({error}); nothing merges until it does",
        )
    if newest is None:
        return True, "main has no completed run yet"
    sha = str(newest.get("head_sha", ""))[:12]
    if newest.get("conclusion") in ("success", "skipped"):
        return True, f"main is green at {sha}"
    if REVERT.match(title):
        return True, f"main is red at {sha}, and this pull request reverts"
    if MENDS.search(body):
        return True, f"main is red at {sha}, and this pull request names what it mends"
    where = newest.get("html_url") or newest.get("id")
    return False, (
        f"main is red at {sha} ({where}): only its repair merges. A repair names "
        '`Mends main: <sha>` in its description; a revert is titled `Revert "..."`'
    )


def failed_tests(log: str) -> list[str]:
    seen: list[str] = []
    for line in log.splitlines():
        for found in FAILED_TEST.finditer(line):
            test = found.group(1)
            if test not in seen:
                seen.append(test)
    return seen


def decide(run: dict[str, Any]) -> str:
    conclusion = run.get("conclusion")
    attempt = int(run.get("run_attempt") or 1)
    on_main = run.get("head_branch") == "main" and run.get("event") == "push"
    if conclusion == "failure":
        if attempt == 1:
            return "rerun"
        return "main-red" if on_main else "none"
    if conclusion == "success":
        if attempt > 1:
            return "flake"
        return "main-green" if on_main else "none"
    return "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    on_guard = sub.add_parser("guard")
    on_guard.add_argument("--runs", type=Path, required=True)
    on_guard.add_argument("--title", required=True)
    on_guard.add_argument("--body-file", type=Path, required=True)
    on_failed = sub.add_parser("failed-tests")
    on_failed.add_argument("--log", type=Path, required=True)
    on_decide = sub.add_parser("decide")
    on_decide.add_argument("--run", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "guard":
        try:
            body = args.body_file.read_text(encoding="utf-8")
        except OSError:
            body = ""
        allowed, why = guard(args.runs, args.title, body)
        print(("ok   " if allowed else "FAIL ") + why)
        return 0 if allowed else 1
    if args.command == "failed-tests":
        log = args.log.read_text(encoding="utf-8", errors="replace") if args.log.exists() else ""
        print("\n".join(failed_tests(log)))
        return 0
    print(decide(json.loads(args.run.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
