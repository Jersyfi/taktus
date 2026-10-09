"""`make gate-usecases` and `make gate-vision` fail on each of their conditions.

The two tools are scripts under `tools/`; each test builds the smallest repository that shows one
condition, in a temporary directory, and runs the tool's `main` against it with `--root`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import check_usecases  # noqa: E402 — a script under tools/, found through the line above
import check_vision  # noqa: E402

NAMES = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
    "theta", "iota", "kappa", "lambda", "mu", "nu", "xi",
]  # fmt: skip

ADR = "# ADR-0001 — A decision\n\n**Status:** accepted\n\nThe decision.\n"


def usecase(
    *,
    state: str = "specified",
    serves: str = "[P1]",
    tests: str = "[]",
    adrs: str | None = None,
    verified_by: str = "A fixture shows the outcome.",
    boundary: str = "Nothing else.",
    extra: str = "",
    proven: str = "",
) -> str:
    return (
        "---\n"
        "id: UC-4.1\n"
        "title: A thing\n"
        "component: run\n"
        f"serves: {serves}\n" + (f"state: {state}\n" if state else "") + "version: 0.1.0\n"
        f"tests: {tests}\n"
        f"adrs: {adrs if adrs is not None else '{}'}\n"
        "supersedes: null\n"
        "---\n\n"
        "# UC-4.1 — A thing\n\n"
        "## 1. What must be achieved\n\nThe outcome.\n\n"
        f"## 2. How it is verified\n\n{verified_by}\n\n"
        f"## 3. Where the boundary lies\n\n{boundary}\n\n"
        f"## 4. What it rests on\n\nNothing.{extra}\n"
        + (f"\n## 5. What is proven so far\n\n{proven}\n" if proven else "")
    )


def git(root: Path, *args: str) -> None:
    # A fixed executable and arguments written in this file: nothing untrusted.
    subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/project-structure.md").write_text(
        "# Structure\n\n## 1. Components\n\n| Component | Owns |\n|---|---|\n"
        "| `run` | runs |\n| `ledger` | the chain |\n\n## 2. Tree\n"
    )
    (root / "docs/roadmap.md").write_text("# Roadmap\n\n### `0.1.0` — first\n")
    (root / "docs/adr").mkdir()
    (root / "docs/adr/ADR-0001-a-decision.md").write_text(ADR)
    vision = root / "docs/vision"
    vision.mkdir(parents=True)
    principles = "".join(
        f"## {n} — Rule {name}\n\nIt says.\n\n**Why.** Because.\n\n**Forbids.** A thing.\n\n"
        for n, name in enumerate(NAMES, 1)
    )
    (vision / "principles.md").write_text("# Principles\n\n" + principles)
    (vision / "market.md").write_text(
        "# Market\n\n> **Stale by construction. Last established: August 2026. Not maintained.**\n"
    )
    (vision / "README.md").write_text("# Vision\n\n[p](principles.md) [m](market.md)\n")
    doctrine = " ".join(f"{n}. Rule {name}." for n, name in enumerate(NAMES, 1))
    (root / "CLAUDE.md").write_text(
        "# Doctrine\n\n## 5. The fourteen guiding principles\n\n"
        f"{doctrine}\n\nMore.\n\n## 6. Next\n"
    )
    (root / "docs/usecases/run").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src/taktus/components/run").mkdir(parents=True)
    (root / "src/taktus/components/run/engine.py").write_text("x = 1\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "work")
    return root


def settle(root: Path) -> None:
    """Commit what is there and make it the base, so that only what follows is the change."""
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "settled")
    git(root, "branch", "-f", "main")


def write(root: Path, text: str, name: str = "docs/usecases/run/UC-4.1-a-thing.md") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def gate(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = check_usecases.main(["--root", str(root), "--base", "main"])
    return code, capsys.readouterr().out


def digest(root: Path) -> str:
    return check_usecases.digest_of(root / "docs/adr/ADR-0001-a-decision.md")


# --- the shape of a use case ---------------------------------------------------------------------


def test_a_well_formed_use_case_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, usecase())
    code, out = gate(repo, capsys)
    assert code == 0, out


def test_a_use_case_without_a_state_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, usecase(state=""))
    code, out = gate(repo, capsys)
    assert code == 1 and "lacks `state`" in out


def test_a_use_case_without_a_verification_condition_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(verified_by=""))
    code, out = gate(repo, capsys)
    assert code == 1 and "`## 2. How it is verified` is empty" in out


def test_a_use_case_serving_no_principle_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(serves="[]"))
    code, out = gate(repo, capsys)
    assert code == 1 and "serves no principle" in out


def test_a_use_case_serving_an_unknown_principle_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(serves="[P15]"))
    code, out = gate(repo, capsys)
    assert code == 1 and "P15" in out


# --- tests named, and green ----------------------------------------------------------------------


@pytest.mark.parametrize("state", ["built", "verified"])
def test_built_or_verified_naming_no_test_fails(
    repo: Path, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    write(repo, usecase(state=state))
    code, out = gate(repo, capsys)
    assert code == 1 and f"state `{state}` names no test" in out


def test_a_named_test_that_does_not_exist_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "tests/test_thing.py").write_text("def test_other() -> None:\n    pass\n")
    write(repo, usecase(state="built", tests="[tests/test_thing.py::test_thing]"))
    code, out = gate(repo, capsys)
    assert code == 1 and "no test function `test_thing`" in out


@pytest.mark.parametrize(
    ("body", "green"),
    [
        ("def test_thing() -> None:\n    assert True\n", True),
        ("def test_thing() -> None:\n    assert False\n", False),
        ("import pytest\n\n\ndef test_thing() -> None:\n    pytest.skip('no')\n", False),
    ],
    ids=["passing", "failing", "skipped"],
)
def test_verified_means_the_named_tests_are_green(
    repo: Path, capsys: pytest.CaptureFixture[str], body: str, green: bool
) -> None:
    (repo / "tests/test_thing.py").write_text(body)
    settle(repo)
    write(repo, usecase(state="verified", tests="[tests/test_thing.py::test_thing]"))
    code, out = gate(repo, capsys)
    assert (code == 0) is green, out
    if not green:
        assert "state `verified`, but" in out


# --- an ADR that moved under a use case ----------------------------------------------------------


def test_an_adr_changed_after_the_check_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(adrs=f"{{ADR-0001: {digest(repo)}}}", extra=" ADR-0001."))
    assert gate(repo, capsys)[0] == 0
    (repo / "docs/adr/ADR-0001-a-decision.md").write_text(ADR + "\nIt now says otherwise.\n")
    code, out = gate(repo, capsys)
    assert code == 1 and "ADR-0001 changed after this use case was checked against it" in out


def test_an_adr_named_but_not_recorded_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(extra=" ADR-0001."))
    code, out = gate(repo, capsys)
    assert code == 1 and "names ADR-0001 but does not record it" in out


# --- a requirement is never changed where it is implemented --------------------------------------


def test_a_new_requirement_with_its_implementation_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase())
    (repo / "src/taktus/components/run/engine.py").write_text("x = 2\n")
    code, out = gate(repo, capsys)
    assert code == 1 and "requirement new, and its implementation too" in out


def test_a_changed_requirement_with_its_implementation_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase())
    settle(repo)
    write(repo, usecase(boundary="Nothing else, and less than before."))
    (repo / "src/taktus/components/run/engine.py").write_text("x = 2\n")
    code, out = gate(repo, capsys)
    assert code == 1 and "requirement changed, and its implementation too" in out


def test_a_changed_description_with_the_implementation_passes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "tests/test_thing.py").write_text("def test_thing() -> None:\n    assert True\n")
    write(repo, usecase())
    settle(repo)
    write(repo, usecase(state="built", tests="[tests/test_thing.py::test_thing]"))
    (repo / "src/taktus/components/run/engine.py").write_text("x = 2\n")
    code, out = gate(repo, capsys)
    assert code == 0, out


def test_what_is_proven_so_far_changes_with_the_implementation(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Section 5 describes the state: the pull request that proves more says so (DEC-0106)."""
    write(repo, usecase(proven="Nothing is built."))
    settle(repo)
    write(repo, usecase(proven="The outcome, by the named test."))
    (repo / "src/taktus/components/run/engine.py").write_text("x = 2\n")
    code, out = gate(repo, capsys)
    assert code == 0, out


def test_what_is_proven_so_far_inside_the_requirement_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(verified_by="A fixture shows it.\n\n**Proven so far:** nothing."))
    code, out = gate(repo, capsys)
    assert code == 1 and "`## 2. How it is verified` states what is proven so far" in out


def test_a_requirement_alone_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, usecase())
    code, out = gate(repo, capsys)
    assert code == 0 and "requirement new; its implementation untouched" in out


# --- the vision layer ----------------------------------------------------------------------------


def vision(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = check_vision.main(["--root", str(root)])
    return code, capsys.readouterr().out


def test_every_principle_served_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, usecase(serves="[" + ", ".join(f"P{n}" for n in range(1, 15)) + "]"))
    code, out = vision(repo, capsys)
    assert code == 0, out


def test_a_principle_no_use_case_serves_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, usecase(serves="[" + ", ".join(f"P{n}" for n in range(1, 14)) + "]"))
    code, out = vision(repo, capsys)
    assert code == 1 and "P14 Rule xi" in out and "no use case serves it" in out


def test_a_principle_titled_otherwise_than_the_doctrine_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = repo / "docs/vision/principles.md"
    path.write_text(path.read_text().replace("## 5 — Rule epsilon", "## 5 — Rule five"))
    code, out = vision(repo, capsys)
    assert code == 1 and "titled 'Rule five'" in out


def test_a_principle_that_forbids_nothing_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = repo / "docs/vision/principles.md"
    text = path.read_text()
    head, _, tail = text.partition("## 3 — Rule gamma")
    path.write_text(head + "## 3 — Rule gamma" + tail.replace("**Forbids.** A thing.", "", 1))
    code, out = vision(repo, capsys)
    assert code == 1 and "principle 3" in out and "no **Forbids.**" in out


def test_a_file_the_readme_does_not_list_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "docs/vision/history.md").write_text("# History\n")
    code, out = vision(repo, capsys)
    assert code == 1 and "does not list history.md" in out


def test_a_market_picture_without_its_warning_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "docs/vision/market.md").write_text("# Market\n\nThe figures.\n")
    code, out = vision(repo, capsys)
    assert code == 1 and "Stale by construction" in out
