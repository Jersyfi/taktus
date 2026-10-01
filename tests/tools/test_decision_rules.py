"""The rule change of DEC-0039, held to its gate: a request raised from DEC-0039 on names the
sources it checked; an `unlisted` notice proposes the entry it was missing; a notice the owner
overrode names the decision; and `make status` counts how often the owner took the recommended
option and how often a notice was overridden."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import check_decisions  # noqa: E402 — a script under tools/, found through the line above
import check_status  # noqa: E402

REGISTER = ROOT / "docs" / "decisions"
SOURCES = (
    "**Sources checked:** docs/vision/principles.md says nothing about it; no ADR decides it; "
    "neither anchors.taktus.md nor anchors.md has an entry; the register has no precedent."
)


def request(tmp_path: Path, number: int, sources: str | None) -> list[str]:
    """An open request in the shape of DEC-0030, renumbered; the problems the gate finds."""
    text = next((REGISTER / "open").glob("DEC-0030-*.md")).read_text(encoding="utf-8")
    text = text.replace("DEC-0030", f"DEC-{number:04d}")
    if sources is not None:
        text = text.replace(
            "## 3. What you must decide", sources + "\n\n## 3. What you must decide"
        )
    path = tmp_path / f"DEC-{number:04d}-a-question.md"
    path.write_text(text, encoding="utf-8")
    doc, problems = check_decisions.parse(path)
    assert doc is not None
    check_decisions.check_open(doc, problems)
    return problems


def test_a_request_from_dec_0039_on_names_the_sources_it_checked(tmp_path: Path) -> None:
    assert any("Sources checked" in p for p in request(tmp_path, 40, None))
    assert not any("Sources checked" in p for p in request(tmp_path, 40, SOURCES))
    partial = "**Sources checked:** the vision says nothing."
    (problem,) = [p for p in request(tmp_path, 41, partial) if "does not name" in p]
    assert "the ADRs" in problem and "the register" in problem


def test_the_requests_raised_before_the_rule_are_left_as_they_are(tmp_path: Path) -> None:
    assert not any("Sources checked" in p for p in request(tmp_path, 30, None))


def notice(tmp_path: Path, kind: str, entry: str, fifth: str | None, **header: str) -> list[str]:
    text = (REGISTER / "NTC-0002-a-missing-adapter-fails-the-step.md").read_text(encoding="utf-8")
    text = text.replace("NTC-0002", "NTC-0099")
    text = re.sub(r"\*\*Mode entry:\*\* M2\.\d", f"**Mode entry:** {entry}", text)
    text = text.replace("**Kind:** behaviour-change", f"**Kind:** {kind}")
    for name, value in header.items():
        text = text.replace("**Decided:**", f"**{name}:** {value}\n**Decided:**", 1)
    if fifth is not None:
        text = text.rstrip() + "\n\n## 5. The entry it proposes\n\n" + fifth + "\n"
    path = tmp_path / "NTC-0099-a-decision.md"
    path.write_text(text, encoding="utf-8")
    doc, problems = check_decisions.parse(
        path,
        prefix="NTC",
        title_pattern=check_decisions.NOTICE_TITLE,
        name_pattern=check_decisions.NOTICE_FILENAME,
    )
    assert doc is not None
    check_decisions.check_notice(doc, problems, check_decisions.anchor_entries())
    return problems


def test_an_unlisted_notice_proposes_the_entry_it_was_missing(tmp_path: Path) -> None:
    proposal = "M1.12 — where a test image is built, the session's."
    assert notice(tmp_path, "unlisted", "M2.6", proposal) == []
    assert any("missing section" in p for p in notice(tmp_path, "unlisted", "M2.6", None))
    assert any("names no entry" in p for p in notice(tmp_path, "unlisted", "M2.6", "the session's"))


@pytest.mark.parametrize(("value", "ok"), [("DEC-0040", True), ("the owner", False)])
def test_an_overridden_notice_names_the_decision(tmp_path: Path, value: str, ok: bool) -> None:
    problems = notice(tmp_path, "behaviour-change", "M2.4", None, **{"Overridden by": value})
    assert (problems == []) is ok, problems


def test_make_status_shows_how_often_the_recommendation_was_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def record(number: int, answer: str) -> None:
        (tmp_path / f"DEC-{number:04d}-x.md").write_text(
            f"# DEC-{number:04d} — x\n\n**Category:** NON-BLOCKING\n\n"
            "### Option A — one (recommended)\n\n### Option B — two\n\n"
            f"## Outcome\n\n**Answer:** {answer}\n",
            encoding="utf-8",
        )

    record(1, "Option A.")
    record(2, "Option A, with one addition.")
    record(3, "Option B.")
    record(4, "Neither, as written: the owner's own.")
    (tmp_path / "DEC-0005-y.md").write_text(
        "# DEC-0005 — y\n\n**Category:** DEFECT\n\n## Outcome\n\n**Corrected:** x\n",
        encoding="utf-8",
    )
    (tmp_path / "NTC-0001-z.md").write_text(
        "# NTC-0001 — z\n\n**Overridden by:** DEC-0004\n", encoding="utf-8"
    )
    (tmp_path / "NTC-0002-z.md").write_text("# NTC-0002 — z\n\n**Kind:** x\n", encoding="utf-8")
    monkeypatch.setattr(check_status, "REGISTER", tmp_path)
    line = check_status.acceptance()
    assert "of 4 answered request(s), 2 took the recommended option (50 %)" in line
    assert "1 another option, 1 an answer of the owner's own" in line
    assert "of 2 notice(s), 1 overridden" in line
