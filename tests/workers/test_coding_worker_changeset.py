"""The coding worker's `changeset` artifact carries the executable bit of every file it lists.

A run hands the changeset to `repository.branches.create`, which writes the branch without a
repository of its own. A file the base does not have arrives with whatever mode the changeset
tells the connector, and without a flag it is a plain file: a script the change adds would fail
with `Permission denied` the first time anything ran it (issue #28, DEC-0020). The worker reads
the mode from the index, where the commit at each step boundary put it.

The worker is a separate deployable and imports nothing from `src/taktus`; the test loads it
from its file and calls the method that builds the artifact on a real workspace.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

WORKER = Path(__file__).resolve().parents[2] / "workers" / "claudecode" / "worker.py"


def load_worker() -> ModuleType:
    specification = importlib.util.spec_from_file_location("coding_worker", WORKER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module  # dataclasses resolve their module by name
    specification.loader.exec_module(module)
    return module


@pytest.mark.skipif(os.name != "posix", reason="the executable bit is a POSIX file mode")
def test_a_new_executable_file_carries_the_flag_and_nothing_else_does(tmp_path: Path) -> None:
    worker = load_worker()
    run = object.__new__(worker._Run)  # only the workspace is needed to build the changeset
    run.workspace = tmp_path

    def git(*args: str) -> None:
        run._git(["git", *args])

    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "old.sh").write_text("#!/bin/sh\n")
    (tmp_path / "tools" / "old.sh").chmod(0o755)
    (tmp_path / "README.md").write_text("# Readme\n")
    git("init", "--quiet")
    git("add", "-A")
    git("commit", "--quiet", "-m", "baseline")
    git("tag", worker.BASELINE_TAG)

    # What an agent might do: add a script and make it executable, add a plain file, change
    # an executable that exists, and remove a file.
    (tmp_path / "tools" / "new.sh").write_text("#!/bin/sh\necho new\n")
    (tmp_path / "tools" / "new.sh").chmod(0o755)
    (tmp_path / "docs.md").write_text("# Docs\n")
    (tmp_path / "tools" / "old.sh").write_text("#!/bin/sh\necho changed\n")
    (tmp_path / "README.md").unlink()
    git("add", "-A")
    git("commit", "--quiet", "-m", "the change")

    changeset = json.loads(run._changeset())
    files = {entry["path"]: entry for entry in changeset["files"]}
    assert files["tools/new.sh"]["executable"] is True, "the new script stays executable"
    assert files["tools/old.sh"]["executable"] is True, "a changed executable says so too"
    assert "executable" not in files["docs.md"], "a plain file carries no flag: additive"
    assert files["docs.md"] == {"path": "docs.md", "content": "# Docs\n", "encoding": "utf-8"}
    assert changeset["deleted"] == ["README.md"]
    head = subprocess.run(  # noqa: S603 — git with fixed arguments in a temporary directory
        ["git", "rev-parse", worker.BASELINE_TAG],  # noqa: S607
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert changeset["base"] == head.stdout.strip()
