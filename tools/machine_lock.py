# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Run a command under the machine's verify lock, so a timing lane runs alone (ADR-0096 §7, #528).

    tools/machine_lock.py shared -- COMMAND...      any number may run at once
    tools/machine_lock.py exclusive -- COMMAND...   runs only while no `shared` one runs

Several sessions run `make verify` on one machine, each in a worktree of the same repository.
A test that asserts a bound on wall-clock time then measures the other sessions as well. Every
lane except `timing` takes the lock shared; `timing` takes it exclusive, so it starts when the
verify runs that are already inside a lane have left it, and no new one enters until it ends.
The lock files are in the repository's common git directory, which all worktrees share.

Two files give the order: a `turnstile` held for the moment a command asks to enter, so a
waiting exclusive one is not starved by a stream of shared ones, and the `runs` lock held for
the command's whole run. A command that has waited for `TAKTUS_LOCK_WAIT_SECONDS` (default 2 700)
runs anyway and says so: a stuck holder never blocks a person's verify for good.

The lock covers what runs through `tools/verify.sh`. A command a person starts by hand, or any
other program, is not in it.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

POLL_SECONDS = 0.5


def common_git_dir() -> Path:
    if os.environ.get("TAKTUS_LOCK_DIR"):  # a test's own directory, so it meets no real verify
        return Path(os.environ["TAKTUS_LOCK_DIR"])
    # A fixed executable name and arguments: nothing untrusted.
    found = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],  # noqa: S607
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    return Path(found).resolve()


def take(handle: int, how: int, deadline: float, what: str) -> bool:
    """Lock `handle` without blocking until `deadline`; False when the time ran out."""
    announced = False
    while True:
        try:
            fcntl.flock(handle, how | fcntl.LOCK_NB)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            if not announced:
                print(f"machine lock: waiting for {what}", file=sys.stderr, flush=True)
                announced = True
            time.sleep(POLL_SECONDS)
        else:
            return True


def run(mode: str, command: list[str]) -> int:
    directory = common_git_dir()
    wait = float(os.environ.get("TAKTUS_LOCK_WAIT_SECONDS", "2700"))
    deadline = time.monotonic() + wait
    turnstile = os.open(directory / "taktus-verify-turnstile.lock", os.O_CREAT | os.O_RDWR)
    runs = os.open(directory / "taktus-verify-runs.lock", os.O_CREAT | os.O_RDWR)
    got_turnstile = take(turnstile, fcntl.LOCK_EX, deadline, "other verify runs to enter a lane")
    if mode == "shared":
        got = got_turnstile and take(runs, fcntl.LOCK_SH, deadline, "a timing lane to end")
        if got_turnstile:
            fcntl.flock(turnstile, fcntl.LOCK_UN)
    else:
        got = got_turnstile and take(runs, fcntl.LOCK_EX, deadline, "other verify runs to leave")
    if not got:
        print(f"machine lock: not taken after {wait:.0f} s; running without it", file=sys.stderr)
    try:
        return subprocess.run(command, check=False).returncode  # noqa: S603
    finally:
        for handle in (runs, turnstile):
            os.close(handle)


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] not in ("shared", "exclusive") or argv[1] != "--":
        print(__doc__)
        return 2
    return run(argv[0], argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
