"""`taktusctl domain` end to end (ADR-0263, UC-15.1): the repository's blueprints are admitted,
a broken one is refused with its findings, and the knowledge blueprint is instantiated in
dialogue across invocations: its tool answered, nothing proposed before its owner, then its
process proposed at level 2, and exported as plain files."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fakes.identity import added_by_command_line

from .test_first_slice import PLAIN, taktusctl

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "blueprints" / "knowledge"
WHO = "idn_ada"


def cli(state: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "domain", *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **PLAIN, **environment(state)},
    )


def environment(state: Path) -> dict[str, str]:
    return {"TAKTUS_STATE_DIR": str(state), "TAKTUS_IDENTITY": WHO}


def shown(done: subprocess.CompletedProcess[str]) -> Any:
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)


def test_the_repository_blueprints_are_admitted_and_a_broken_one_is_refused(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    directories = sorted(str(p.parent) for p in (ROOT / "blueprints").glob("*/blueprint.yaml"))
    done = cli(state, "check", *directories)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.count("admitted   ") == len(directories) == 4

    broken = tmp_path / "broken"
    shutil.copytree(KNOWLEDGE, broken)
    path = broken / "blueprint.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("value_criteria:", "unvalued:"), encoding="utf-8"
    )
    done = cli(state, "check", str(broken))
    assert done.returncode == 1
    assert "its value criteria name no cost" in done.stdout


def test_a_domain_is_instantiated_in_dialogue_from_the_command_line(tmp_path: Path) -> None:
    state = tmp_path / "state"
    added_by_command_line(taktusctl(), WHO, {**os.environ, **environment(state)})
    blueprint = ("--blueprint", str(KNOWLEDGE))

    started = shown(cli(state, "start", *blueprint))
    instance = started["id"]
    assert [q["kind"] for q in started["questions"]] == ["capability", "owner"]
    [asked] = [q for q in started["questions"] if q["kind"] == "capability"]
    assert asked["subject"] == "knowledge.documents" and asked["options"]

    answered = shown(
        cli(state, "answer", instance, "knowledge.documents", asked["options"][0], *blueprint)
    )
    assert [q["kind"] for q in answered["questions"]] == ["owner"]

    refused = cli(state, "propose", instance, *blueprint)
    assert refused.returncode == 1 and "Who owns this domain" in refused.stderr

    shown(cli(state, "owner", instance, WHO, *blueprint))
    proposed = shown(cli(state, "propose", instance, *blueprint))
    [made] = proposed["proposed"]
    assert made["process_id"] == "k-01" and made["level"] == 2
    assert proposed["questions"] == []

    show = shown(cli(state, "show", instance, *blueprint))
    assert show["figures"]["domain"] == "knowledge" and show["figures"]["runs"] == 0

    target = tmp_path / "export"
    done = cli(state, "export", str(KNOWLEDGE), str(target))
    assert done.returncode == 0, done.stderr
    assert (target / "blueprint.yaml").read_bytes() == (KNOWLEDGE / "blueprint.yaml").read_bytes()
    assert (target / "processes" / "K-01-answer-from-knowledge.yaml").is_file()
