"""Every tracked path belongs to a lane of CI (ADR-0096 §3, #390).

`tools/lanes.py` selects the lanes a change runs. A path that no selectable lane claims, that
selects nothing more than the always-on checks and is not documentation, could change without
any test running on it. This test fails on such a path, so that a new directory is given a
lane when it is added.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import lanes  # noqa: E402 — a script under tools/, found through the line above


def test_no_tracked_path_escapes_every_lane() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],  # noqa: S607 — a fixed command
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()  # fmt: skip
    assert lanes.holes(tracked) == []
