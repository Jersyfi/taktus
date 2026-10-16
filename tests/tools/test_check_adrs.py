"""`make gate-adrs` fails a reference to an ADR that does not exist, and passes one that does.

Each test builds the smallest repository that shows the condition, in a temporary directory that
is not a Git repository, so the tool reads every file under it, and runs the tool's `main`
against it with `--root`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import check_adrs  # noqa: E402 — a script under tools/, found through the line above

# Spelt in two halves, so this file names no ADR that the repository's own gate would resolve.
MISSING = "ADR-" + "9999"


def repository(root: Path, reference: str, where: str = "docs/notes.md") -> None:
    adrs = root / "docs" / "adr"
    adrs.mkdir(parents=True)
    (adrs / "ADR-0001-a-decision.md").write_text(
        "# ADR-0001 — A decision\n\n**Status:** accepted\n\nThe decision.\n", encoding="utf-8"
    )
    (adrs / "README.md").write_text("[0001](ADR-0001-a-decision.md)\n", encoding="utf-8")
    target = root / where
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"First line.\nAs {reference} decided.\n", encoding="utf-8")


def test_an_existing_reference_passes(tmp_path: Path) -> None:
    repository(tmp_path, "ADR-0001")
    assert check_adrs.main(["--root", str(tmp_path)]) == 0


@pytest.mark.parametrize("where", ["docs/notes.md", "src/x/module.py", "deploy/values.yaml"])
def test_a_missing_reference_fails_naming_file_and_line(
    tmp_path: Path, where: str, capsys: pytest.CaptureFixture[str]
) -> None:
    repository(tmp_path, MISSING, where)
    assert check_adrs.main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert f"FAIL {where}:2" in out
    assert MISSING in out


def test_a_reference_outside_the_resolved_places_is_not_read(tmp_path: Path) -> None:
    repository(tmp_path, MISSING, "web/notes.md")
    assert check_adrs.main(["--root", str(tmp_path)]) == 0
