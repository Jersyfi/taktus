"""`taktusctl bundle check` end to end (#407, ADR-0113 §4): a bundle is held to registration's
rules with no instance, no database, no login and no network.

The command runs as a repository's CI would run it: its own process, in a directory outside this
repository, with an environment that holds nothing of Taktus — no database URL, no identity, no
state directory, no proxy. Every bundle of this repository passes. A bundle registration would
refuse is refused with the same findings registration gives, because it is the same code
(`parse_bundle`). The CI snippet `examples/README.md` documents is a workflow that runs it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess

from .test_first_slice import PLAIN, taktusctl

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "processes" / "six-times-seven.yaml"
BLUEPRINT = ROOT / "blueprints" / "self-operation" / "blueprint.yaml"
SNIPPET = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def check(*paths: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    """The command in a bare environment: the path to find programs on, a home that is empty,
    and nothing else."""
    home = cwd / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "bundle", "check", *map(str, paths)],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env={"PATH": os.environ["PATH"], "HOME": str(home), **PLAIN},
    )


def refused_bundle() -> dict[str, Any]:
    """The example with an exact step that declares no check: registration refuses it."""
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for step in document["steps"]:
        if step.get("exactness") == "exact":
            step.pop("checks", None)
    return dict(document)


def test_every_bundle_of_the_repository_passes_with_nothing_of_an_instance(
    tmp_path: Path,
) -> None:
    result = check(ROOT / "blueprints", ROOT / "examples" / "processes", cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    bundles = [*sorted(ROOT.glob("blueprints/*/processes/*.yaml")), EXAMPLE]
    for path in bundles:
        assert f"ok         {path}" in result.stdout
    assert "3 file(s) skipped as no process" in result.stdout, (
        "the two blueprint.yaml and software-operations' stages.yaml (ADR-0137)"
    )
    assert "Not checked without an instance" in result.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["home"], "it left nothing behind"
    assert not any((tmp_path / "home").iterdir())


def test_a_bundle_registration_refuses_is_refused_with_registration_s_findings(
    tmp_path: Path,
) -> None:
    document = refused_bundle()
    try:
        parse_bundle(document)
    except InvalidProcess as error:
        findings = error.findings
    else:
        raise AssertionError("the bundle should be refused at registration")
    bad = tmp_path / "bundles" / "refused.yaml"
    bad.parent.mkdir()
    bad.write_text(yaml.safe_dump(document), encoding="utf-8")
    (tmp_path / "bundles" / "good.yml").write_text(EXAMPLE.read_text(encoding="utf-8"))
    result = check(tmp_path / "bundles", cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"refused    {bad}" in result.stdout
    for finding in findings:
        assert f"  - {finding}" in result.stdout
    assert "ok         " in result.stdout and "good.yml" in result.stdout
    assert "1 would register, 1 refused" in result.stdout


def test_a_file_it_cannot_read_or_nothing_to_check_is_its_own_exit_code(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("steps: [unclosed\n", encoding="utf-8")
    result = check(broken, cwd=tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"unreadable {broken}" in result.stdout
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check(empty, cwd=tmp_path).returncode == 2, "a directory holding no bundle"


def test_a_blueprint_named_itself_is_checked_and_refused(tmp_path: Path) -> None:
    """Below a directory, a file whose `kind` says it is no process is skipped; named itself, it
    is held to the rules, so that nothing a person asked for is skipped without a word."""
    result = check(BLUEPRINT, cwd=tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "a bundle lists at least one step under `steps`" in result.stdout


def test_the_documented_ci_snippet_is_a_workflow_that_runs_the_check() -> None:
    text = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    snippets = [s for s in SNIPPET.findall(text) if "taktusctl bundle check" in s]
    assert len(snippets) == 1, "examples/README.md documents one CI snippet"
    workflow = yaml.safe_load(snippets[0])
    steps = [step for job in workflow["jobs"].values() for step in job["steps"]]
    runs = [step["run"] for step in steps if "run" in step]
    assert any("taktusctl bundle check" in run for run in runs)
    assert not [s for s in runs if "TAKTUS_" in s], "it configures nothing of an instance"
    assert "secrets." not in snippets[0], "it needs no credential"
