"""The first process of the administration guide runs with nothing outside Taktus (#445).

`examples/processes/first-process.yaml` is what a new instance registers and runs as the last
step of `docs/guides/administration/first-install.md`. It needs no worker, no connector and no
model. Each step waits for a person at level 2, is confirmed, and the run finishes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fakes.identity import added_by_command_line

from .test_first_slice import PLAIN, taktusctl

FIRST = Path(__file__).resolve().parents[2] / "examples" / "processes" / "first-process.yaml"


def test_the_first_process_runs_on_confirmation_alone(tmp_path: Path) -> None:
    env = {**os.environ, **PLAIN, "TAKTUS_STATE_DIR": str(tmp_path / "state")}
    env.pop("TAKTUS_WORKER", None)
    added_by_command_line(taktusctl(), "idn_test", env)
    command = [taktusctl(), "run", "--process", str(FIRST)]
    confirmed: list[str] = []
    for _ in range(5):
        done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # noqa: S603 — our own entry point
        if done.returncode == 0:
            break
        assert done.returncode == 3, done.stdout + done.stderr
        waiting = [line for line in done.stdout.splitlines() if "waits for a person:" in line]
        assert waiting, done.stdout + done.stderr
        hint = waiting[0]
        run_id = hint.split("--resume ", 1)[1].split()[0]
        step = hint.split()[-1]
        confirmed.append(step)
        command = [
            taktusctl(),
            "run",
            "--process",
            str(FIRST),
            "--resume",
            run_id,
            "--approve",
            step,
        ]
    assert done.returncode == 0, done.stdout + done.stderr
    assert confirmed == ["greet", "settle", "confirm"]
