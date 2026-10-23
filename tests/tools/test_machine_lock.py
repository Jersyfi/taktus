"""`tools/machine_lock.py` lets a timing lane run alone (ADR-0096 §7, issue #528)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "machine_lock.py"


def started(where: Path, mode: str, code: str, wait: str = "30") -> subprocess.Popen[str]:
    """`code` run under the lock, with the lock files in `where`: a test meets no real verify."""
    return subprocess.Popen(  # noqa: S603 — this repository's tool and Python
        [sys.executable, str(TOOL), mode, "--", sys.executable, "-c", code],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "TAKTUS_LOCK_WAIT_SECONDS": wait, "TAKTUS_LOCK_DIR": str(where)},
    )  # fmt: skip


def test_a_command_gives_back_its_exit_code(tmp_path: Path) -> None:
    process = started(tmp_path, "shared", "raise SystemExit(3)")
    process.communicate(timeout=30)
    assert process.returncode == 3


def test_shared_commands_run_together(tmp_path: Path) -> None:
    first = started(tmp_path, "shared", "import time; time.sleep(3)")
    time.sleep(0.7)
    second = started(tmp_path, "shared", "print('ran')")
    out, _ = second.communicate(timeout=2.5)
    assert out.strip() == "ran", "the second did not wait for the first"
    first.communicate(timeout=30)


def test_an_exclusive_command_waits_for_a_shared_one_and_holds_the_rest_back(
    tmp_path: Path,
) -> None:
    holder = started(tmp_path, "shared", "import time; time.sleep(3)")
    time.sleep(0.7)
    alone = started(
        tmp_path,
        "exclusive",
        "import time; print(time.time()); time.sleep(2); print(time.time())",
    )
    time.sleep(0.7)
    later = started(tmp_path, "shared", "import time; print(time.time())")
    waited_from = time.time()
    begin, end = (float(n) for n in alone.communicate(timeout=30)[0].split())
    after = float(later.communicate(timeout=30)[0])
    holder.communicate(timeout=30)
    assert begin - waited_from > 0.5, "the exclusive command started beside a shared one"
    assert after >= end - 0.05, "a shared command entered while the exclusive one was running"


def test_a_command_waits_no_longer_than_its_limit(tmp_path: Path) -> None:
    holder = started(tmp_path, "exclusive", "import time; time.sleep(4)")
    time.sleep(0.7)
    impatient = started(tmp_path, "shared", "print('ran')", wait="1")
    out, err = impatient.communicate(timeout=30)
    holder.communicate(timeout=30)
    assert out.strip() == "ran"
    assert "running without it" in err
