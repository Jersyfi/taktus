"""Run a pytest gate that may have no targets yet.

Runs as `uv run tools/gate.py <name> [--workers N|auto] <pytest arguments>`. A gate with nothing
to check reports green and says so; it does not fail. pytest exits 5 when it collected no tests,
and that is the one exit code this wrapper turns into success. Every other code — a failing test,
a usage error, a path that does not exist — passes through unchanged, so a typo in a gate's path
still fails.

`--workers` spreads the tests over that many processes with pytest-xdist, one test file per
process at a time (`--dist loadfile`), so that the tests of one file keep what they share; `0`
runs them in this process. Without it the gate runs serially, as a suite that cannot share a
machine with itself must (issue #388).

Every gate prints its duration as its last line, with the number of processes it ran on. A suite
that has become too slow to be useful is a finding reported with its cost before and after
(CLAUDE.md §11), and this line is where the cost is read from, in every log of every run.
"""

from __future__ import annotations

import sys
import time

import pytest
from pytest import ExitCode


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: gate.py <name> [--workers N|auto] <pytest arguments>")
        return 2
    name, *args = argv
    spread = "serially"
    if args[:1] == ["--workers"]:
        if len(args) < 2:
            print("usage: gate.py <name> [--workers N|auto] <pytest arguments>")
            return 2
        spread = f"on {args[1]} workers"
        args = ["-n", args[1], "--dist", "loadfile", *args[2:]]
    started = time.monotonic()
    code = pytest.main(args)
    print(f"gate {name}: {time.monotonic() - started:.1f}s, {spread}")
    if code == ExitCode.NO_TESTS_COLLECTED:
        print(f"gate {name}: no targets yet — nothing to check, reporting green")
        return 0
    return int(code)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
