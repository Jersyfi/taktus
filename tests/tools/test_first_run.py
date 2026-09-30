"""`tools/first_run.sh` refuses an invocation it cannot run before it reads a credential,
starts a process or asks the repository anything.

The script is the one command for the live end-to-end, and since issue #30 it runs one bundle
alone (`--only`, `--from`) and continues a stopped run (`--resume`). What it does with the
output of `taktusctl run` — P-02's "already done" and P-03's leftover branch — is held against
the real output in `tests/integration/test_dev_orchestration.py`; this file holds the options.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "first_run.sh"


def first_run(*arguments: str) -> subprocess.CompletedProcess[str]:
    # Only invocations the script refuses before it reads `.env` are run here: a checkout's
    # `.env` may hold real credentials, and a valid invocation would use them.
    environment = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    return subprocess.run(  # noqa: S603 — the repository's own script, fixed arguments
        ["sh", str(SCRIPT), *arguments],  # noqa: S607
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ((), "usage: tools/first_run.sh <issue number>"),
        (("eleven",), "usage: tools/first_run.sh <issue number>"),
        (("11", "12"), "one issue at a time"),
        (("11", "--only"), "--only needs a value"),
        (("11", "--only", "P-04"), "there is no bundle P-04 here"),
        (("11", "--from", "P-01"), "there is no bundle P-01 here"),
        (("11", "--only", "P-03", "--from", "P-02"), "--only and --from exclude each other"),
        (("11", "--resume", "run_0123"), "--resume continues one run: name its bundle"),
        (("11", "--bogus"), "unknown option --bogus"),
    ],
)
def test_an_invocation_it_cannot_run_is_refused_first(
    arguments: tuple[str, ...], says: str
) -> None:
    completed = first_run(*arguments)
    assert completed.returncode == 2, completed.stderr
    assert says in completed.stderr, completed.stderr
    assert "TAKTUS_CREDENTIAL" not in completed.stderr, "refused before any credential is read"


def test_help_prints_the_usage() -> None:
    completed = first_run("--help")
    assert completed.returncode == 0
    assert "--only P-02|P-03" in completed.stdout and "--resume RUN_ID" in completed.stdout
