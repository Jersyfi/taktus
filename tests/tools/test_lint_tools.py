"""`make lint` type-checks the repository's tools as strictly as the product (issue #142).

`make lint` runs `mypy` with no arguments, so what it checks is what `[tool.mypy]` in
`pyproject.toml` names. These tests read that configuration, and run `mypy` the way the target
does with one tool's text replaced by a version carrying a wrong annotation.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"


def mypy_configuration() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        configuration: dict[str, object] = tomllib.load(handle)["tool"]["mypy"]
    return configuration


def test_every_tool_is_among_what_lint_checks_strictly() -> None:
    configuration = mypy_configuration()
    assert configuration.get("strict") is True
    files = configuration.get("files")
    assert isinstance(files, list)
    targets = [ROOT / name for name in files]
    tools = sorted(TOOLS.glob("*.py"))
    assert tools
    unchecked = [
        tool.name
        for tool in tools
        if not any(tool == target or target in tool.parents for target in targets)
    ]
    assert unchecked == []
    assert ROOT / "src" / "taktus" in targets


def test_a_wrong_annotation_in_a_tool_fails_lint(tmp_path: Path) -> None:
    tool = TOOLS / "gate.py"
    shadow = tmp_path / "gate.py"
    shadow.write_text(tool.read_text() + '\n\nWRONG: int = "not a number"\n')
    result = subprocess.run(  # noqa: S603 - the interpreter running the tests, fixed arguments
        [
            sys.executable,
            "-m",
            "mypy",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--shadow-file",
            str(tool),
            str(shadow),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "tools/gate.py" in result.stdout
    assert "[assignment]" in result.stdout
