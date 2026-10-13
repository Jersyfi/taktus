"""Record numbers never collide and the register's index is stored nowhere (#316, DEC-0189
rule 6): a number is reserved on the remote before its record is written, two sessions never
get the same one, two pull requests that each add a record merge in either order without a
conflict, and the gate fails a record added under a number nobody reserved.

Every test works on a bare repository in a temporary directory standing in for the remote,
with two clones standing in for two sessions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above
import reserve  # noqa: E402

REGISTER = "docs/decisions"


def git(cwd: Path, *args: str) -> str:
    return reserve.git(*args, cwd=cwd).stdout


def write(clone: Path, name: str, text: str = "x\n") -> None:
    path = clone / REGISTER / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def sessions(tmp_path: Path) -> tuple[Path, Path]:
    """A remote whose `main` holds NTC-0001 and DEC-0001, and two clones of it."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--quiet", "--bare", "-b", "main", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "--quiet", str(remote), str(seed))
    write(seed, "NTC-0001-a-notice.md")
    write(seed, "DEC-0001-a-decision.md")
    write(seed, "README.md", "The index is printed by `make register`.\n")
    git(seed, "symbolic-ref", "HEAD", "refs/heads/main")
    git(seed, "add", ".")
    git(seed, "commit", "--quiet", "-m", "seed")
    git(seed, "push", "--quiet", "origin", "main")
    first, second = tmp_path / "first", tmp_path / "second"
    git(tmp_path, "clone", "--quiet", str(remote), str(first))
    git(tmp_path, "clone", "--quiet", str(remote), str(second))
    return first, second


def test_two_sessions_never_get_the_same_number(sessions: tuple[Path, Path]) -> None:
    first, second = sessions
    assert reserve.reserve("NTC", cwd=first) == "NTC-0002"
    assert reserve.reserve("NTC", cwd=second) == "NTC-0003"
    assert reserve.reserve("DEC", cwd=second) == "DEC-0002"
    assert set(reserve.reservations(cwd=first)) == {"NTC-0002", "NTC-0003", "DEC-0002"}


def test_a_session_that_lost_the_race_takes_the_next_number(
    sessions: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = sessions
    assert reserve.reserve("NTC", cwd=first) == "NTC-0002"
    # The second session counted before the first reserved: it tries NTC-0002 too.
    monkeypatch.setattr(reserve, "held", lambda prefix, remote, cwd: {1})
    assert reserve.reserve("NTC", cwd=second) == "NTC-0003"
    reserved = reserve.reservations(cwd=first)
    assert reserved["NTC-0002"] != reserved["NTC-0003"]


def test_a_number_a_branch_holds_without_a_reservation_is_skipped(
    sessions: tuple[Path, Path],
) -> None:
    first, second = sessions
    git(first, "checkout", "--quiet", "-b", "older-branch")
    write(first, "NTC-0005-taken-by-hand.md")
    git(first, "add", ".")
    git(first, "commit", "--quiet", "-m", "a record from before reservations")
    git(first, "push", "--quiet", "origin", "older-branch")
    assert reserve.reserve("NTC", cwd=second) == "NTC-0006"


def test_a_number_is_reserved_exactly_once(sessions: tuple[Path, Path]) -> None:
    first, second = sessions
    assert reserve.reserve(identifier="NTC-0007", cwd=first) == "NTC-0007"
    with pytest.raises(reserve.ReservationError, match="reserved already"):
        reserve.reserve(identifier="NTC-0007", cwd=second)
    with pytest.raises(reserve.ReservationError, match="record on origin/main"):
        reserve.reserve(identifier="NTC-0001", cwd=second)
    with pytest.raises(reserve.ReservationError, match="is not"):
        reserve.reserve(identifier="NTC-7", cwd=second)


@pytest.mark.parametrize("order", [("first", "second"), ("second", "first")])
def test_two_pull_requests_that_each_add_a_record_merge_in_either_order(
    sessions: tuple[Path, Path], order: tuple[str, str]
) -> None:
    clones = dict(zip(("first", "second"), sessions, strict=True))
    for name, clone in clones.items():
        identifier = reserve.reserve("NTC", cwd=clone)
        git(clone, "checkout", "--quiet", "-b", name)
        write(clone, f"{identifier}-from-{name}.md")
        git(clone, "add", ".")
        git(clone, "commit", "--quiet", "-m", f"add {identifier}")
        git(clone, "push", "--quiet", "origin", name)
    merger = clones["first"]
    git(merger, "fetch", "--quiet", "origin")
    git(merger, "checkout", "--quiet", "main")
    git(merger, "reset", "--quiet", "--hard", "origin/main")
    for name in order:
        # A squash merge, as the host makes it; a conflict raises here.
        git(merger, "merge", "--quiet", "--squash", f"origin/{name}")
        git(merger, "commit", "--quiet", "-m", f"squash {name}")
    names = sorted(path.name for path in (merger / REGISTER).glob("NTC-*.md"))
    assert names == [
        "NTC-0001-a-notice.md",
        "NTC-0002-from-first.md",
        "NTC-0003-from-second.md",
    ]
    readme = (merger / REGISTER / "README.md").read_text(encoding="utf-8")
    assert readme == "The index is printed by `make register`.\n"


def document(name: str) -> check_decisions.Document:
    number = name.split("-")[1]
    return check_decisions.Document(Path(name), number, "x", {}, {})


def test_the_gate_fails_a_record_added_without_a_reservation(
    sessions: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = sessions
    monkeypatch.setattr(check_decisions, "ROOT", first)
    reserved = reserve.reserve("NTC", cwd=first)
    docs = [
        document("NTC-0001-a-notice.md"),
        document(f"{reserved}-reserved.md"),
        document("NTC-0009-by-hand.md"),
    ]
    report = check_decisions.Report()
    check_decisions.check_reserved(report, docs, "origin/main", "origin")
    (failure,) = report.failures
    assert failure.startswith("NTC-0009") and "make reserve" in failure
    assert report.passed == 1, "the reserved record passes; the one on main is not added"


# --- the index is generated and stored nowhere ---------------------------------------------------


def test_the_index_files_every_record_in_its_own_table() -> None:
    register = ROOT / REGISTER
    records = [
        doc
        for path in sorted(register.glob("DEC-0001-*.md"))
        if (doc := check_decisions.parse(path)[0])
    ]
    notices = [
        doc
        for path in sorted(register.glob("NTC-0001-*.md"))
        if (
            doc := check_decisions.parse(
                path,
                prefix="NTC",
                title_pattern=check_decisions.NOTICE_TITLE,
                name_pattern=check_decisions.NOTICE_FILENAME,
            )[0]
        )
    ]
    text = check_decisions.index_text(records, notices, [])

    def section(heading: str) -> str:
        return text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]

    assert "NTC-0001-" in section("Notices") and "NTC-0001-" not in section("Decisions")
    assert "DEC-0001-" in section("Decisions") and "DEC-0001-" not in section("Notices")
    assert "NTC-0001-" not in section("Needs")


def test_a_row_stored_in_the_register_readme_fails_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    readme = tmp_path / "README.md"
    monkeypatch.setattr(check_decisions, "INDEX", readme)
    monkeypatch.setattr(check_decisions, "ROOT", tmp_path)
    readme.write_text("The index is printed by `make register`.\n", encoding="utf-8")
    report = check_decisions.Report()
    check_decisions.check_index(report)
    assert report.failures == []
    readme.write_text(
        "`make register`\n\n| [0001](NTC-0001-a-notice.md) | A notice | M2.1 |\n",
        encoding="utf-8",
    )
    check_decisions.check_index(report)
    (failure,) = report.failures
    assert "stores a row of the index" in failure
    readme.write_text("No pointer.\n", encoding="utf-8")
    check_decisions.check_index(report)
    assert "make register" in report.failures[-1]
