"""`taktusctl skill export` (UC-14.3): a skill registered from its directory is written back as
that directory, byte for byte, one by one and as a bundle `skills/<name>/`, readable without
Taktus."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from taktus.adapters.driving.cli.bundle_command import skill_on_disk

from .test_first_slice import PLAIN, taktusctl

SKILL = """---
name: triage
description: Sorts an incoming ticket into one of the team's queues.
license: Apache-2.0
---

Read the ticket. Name the queue from `queues.md` it belongs in, and why.
"""
QUEUES = "- billing\n- delivery\n- returns\n"


def cli(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_a_skill_is_exported_as_the_directory_it_was_registered_from(tmp_path: Path) -> None:
    state = tmp_path / "state"
    source = tmp_path / "source" / "skills" / "triage"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(SKILL, "utf-8")
    (source / "queues.md").write_text(QUEUES, "utf-8")
    registered = cli(state, "skill", "register", str(tmp_path / "source"), "--version", "1")
    assert registered.returncode == 0, registered.stdout + registered.stderr

    one = cli(state, "skill", "export", "triage@1", "--to", str(tmp_path / "one"))
    assert one.returncode == 0, one.stdout + one.stderr
    written = tmp_path / "one" / "skills" / "triage"
    assert (written / "SKILL.md").read_text("utf-8") == SKILL
    assert (written / "queues.md").read_text("utf-8") == QUEUES
    assert skill_on_disk(written).digest == skill_on_disk(source).digest

    bundle = cli(state, "skill", "export", "--to", str(tmp_path / "bundle"))
    assert bundle.returncode == 0, bundle.stdout + bundle.stderr
    assert "no skill to export" in bundle.stdout, "a draft is not in the hub's bundle"
