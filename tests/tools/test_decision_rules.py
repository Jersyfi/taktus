"""The rule change of DEC-0039 and the owner's answers DEC-0040 to DEC-0042, held to their gate:
a request raised from DEC-0039 on names the sources it checked; an `unlisted` notice proposes the
entry it was missing; an `unlisted` or `restoration` notice states how it follows its source; a
notice the owner overrode names the decision; the override rate goes to the owner after every
twenty unlisted notices; a mode-4 request recommends nothing (DEC-0045); every need named
resolves to one that will be or was provided, every `TODO(owner)` to an open record, and every
credential variable has the one form; and `make status` counts how often the owner took the
recommended option — of the requests asked before they were answered — and how often a notice
was overridden."""

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
    """An open request in the shape of DEC-0030, renumbered; the problems the gate finds.

    Built from DEC-0030's record, which never moves again, with its outcome taken off and a
    provisional answer put back — so that the test does not depend on what is open today."""
    text = next(REGISTER.glob("DEC-0030-*.md")).read_text(encoding="utf-8")
    text = text.split("\n## Outcome", 1)[0] + "\n"
    text = text.replace(
        "**Needed by:**", "**Provisional answer:** Option A, marked here.\n**Needed by:**", 1
    )
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


FOLLOWS = {
    "How it follows": "CLAUDE.md §9 says what the session can derive is not asked, and this "
    "derivation used only what the owner provided for it."
}


def test_an_unlisted_notice_proposes_the_entry_it_was_missing(tmp_path: Path) -> None:
    proposal = "M1.12 — where a test image is built, the session's."
    assert notice(tmp_path, "unlisted", "M2.6", proposal, **FOLLOWS) == []
    assert any(
        "missing section" in p for p in notice(tmp_path, "unlisted", "M2.6", None, **FOLLOWS)
    )
    unnamed = notice(tmp_path, "unlisted", "M2.6", "the session's", **FOLLOWS)
    assert any("names no entry" in p for p in unnamed)


@pytest.mark.parametrize(
    ("kind", "entry", "fifth"), [("unlisted", "M2.6", "M1.12 — x."), ("restoration", "M2.7", None)]
)
def test_a_notice_that_decides_by_a_source_states_how_it_follows(
    tmp_path: Path, kind: str, entry: str, fifth: str | None
) -> None:
    assert notice(tmp_path, kind, entry, fifth, **FOLLOWS) == []
    (problem,) = notice(tmp_path, kind, entry, fifth)
    assert "How it follows" in problem and "DEC-0040" in problem
    named_only = notice(tmp_path, kind, entry, fifth, **{"How it follows": "the vision."})
    assert any("How it follows" in p for p in named_only), "naming a source is not following it"


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
    assert (
        "of 4 request(s) asked before they were answered, 2 took the recommended option (50 %)"
        in line
    )
    assert "1 another option, 1 an answer of the owner's own" in line
    assert "of 2 notice(s), 1 overridden" in line


# --- the override review (DEC-0042) -----------------------------------------------------------


def test_the_override_rate_goes_to_the_owner_after_every_twenty_unlisted_notices() -> None:
    def doc(number: int, **fields: str) -> check_decisions.Document:
        return check_decisions.Document(Path("x"), f"{number:04d}", "x", fields, {})

    unlisted = [doc(n, Kind="unlisted") for n in range(19)]
    report = check_decisions.Report()
    check_decisions.check_override_review(report, unlisted, [])
    assert not report.failures
    report = check_decisions.Report()
    check_decisions.check_override_review(report, [*unlisted, doc(99, Kind="unlisted")], [])
    assert report.failures and "Override review" in report.failures[0]
    report = check_decisions.Report()
    review = doc(50, **{"Override review": "of 20 unlisted notices, 2 overridden (10 %)"})
    check_decisions.check_override_review(report, [*unlisted, doc(99, Kind="unlisted")], [review])
    assert not report.failures


# --- a mode-4 request, and a request with no date of its own (DEC-0045) -------------------------


def licence(tmp_path: Path, recommended: bool, needed_by: str) -> list[str]:
    # Open or answered, the file is read as the request it was: the test must not break the day
    # the owner decides the licence.
    found = next(REGISTER.rglob("DEC-0044-*.md"))
    text = found.read_text(encoding="utf-8").split("\n## Outcome", 1)[0] + "\n"
    if recommended:
        text = text.replace("for the contracts\n", "for the contracts (recommended)\n", 1)
    text = text.replace(
        "**Needed by:** before 1.0.0, and before the first contribution from outside is accepted",
        f"**Needed by:** {needed_by}",
    )
    path = tmp_path / "DEC-0044-the-licence.md"
    path.write_text(text, encoding="utf-8")
    doc, problems = check_decisions.parse(path)
    assert doc is not None
    check_decisions.check_open(doc, problems)
    return problems


def test_a_mode_4_request_supplies_options_and_recommends_none(tmp_path: Path) -> None:
    assert licence(tmp_path, False, "before 1.0.0") == []
    (problem,) = licence(tmp_path, True, "before 1.0.0")
    assert "mode-4" in problem and "DEC-0045" in problem


def test_needed_by_is_a_date_or_what_the_answer_must_precede(tmp_path: Path) -> None:
    assert licence(tmp_path, False, "2026-12-31") == []
    assert any("Needed by" in p for p in licence(tmp_path, False, "some day"))


# --- references to needs and owner actions (ADR-0028) -------------------------------------------


def need(tmp_path: Path, number: int, superseded: bool) -> check_decisions.Document:
    fields = "**Superseded by:** NEED-0007\n" if superseded else ""
    text = f"# NEED-{number:04d} — x\n\n## Outcome\n\n**Provided:** 2026-09-23\n{fields}"
    path = tmp_path / f"NEED-{number:04d}-x.md"
    path.write_text(text, encoding="utf-8")
    doc, _ = check_decisions.parse(
        path,
        prefix="NEED",
        title_pattern=check_decisions.NEED_TITLE,
        name_pattern=check_decisions.NEED_FILENAME,
    )
    assert doc is not None
    return doc


def references(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> list[str]:
    monkeypatch.setattr(check_decisions, "ROOT", tmp_path)
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    open_needs = [need(tmp_path, 7, superseded=False)]
    provided = [need(tmp_path, 1, superseded=False), need(tmp_path, 4, superseded=True)]
    open_dec = check_decisions.Document(tmp_path / "d", "0044", "x", {}, {})
    report = check_decisions.Report()
    check_decisions.check_references(report, open_needs, provided, [open_dec], paths)
    return report.failures


def test_a_need_named_resolves_to_one_that_will_be_or_was_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert references(tmp_path, monkeypatch, {"CREDENTIALS.md": "NEED-0001, NEED-0007"}) == []
    (missing,) = references(tmp_path, monkeypatch, {"a.md": "under NEED-0099"})
    assert "NEED-0099 has no file" in missing
    (superseded,) = references(tmp_path, monkeypatch, {"CREDENTIALS.md": "| x | NEED-0004 |"})
    assert "CREDENTIALS.md:1" in superseded and "superseded" in superseded
    history = {"docs/decisions/README.md": "NEED-0004, superseded by NEED-0007"}
    assert references(tmp_path, monkeypatch, history) == [], "the register keeps its history"


def test_an_action_left_to_the_owner_is_an_open_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert references(tmp_path, monkeypatch, {"a.py": "# TODO(owner): NEED-0007"}) == []
    assert references(tmp_path, monkeypatch, {"a.py": "# TODO(owner): DEC-0044"}) == []
    (bare,) = references(tmp_path, monkeypatch, {"a.py": "# TODO(owner): set the label"})
    assert "TODO(owner)" in bare
    (closed,) = references(tmp_path, monkeypatch, {"a.py": "# TODO(owner): NEED-0001"})
    assert "names no open" in closed
    quoted = {"README.md": "every `TODO(owner)` names an open record"}
    assert references(tmp_path, monkeypatch, quoted) == [], "the rule described is no action"


def test_a_superseded_need_says_what_took_its_place(tmp_path: Path) -> None:
    text = (
        "# NEED-0004 — x\n\n## Outcome\n\n**Provided:** 2026-09-23\n"
        "**How:** superseded, not answered.\n"
    )
    path = tmp_path / "NEED-0004-x.md"
    path.write_text(text, encoding="utf-8")
    doc, problems = check_decisions.parse(
        path,
        prefix="NEED",
        title_pattern=check_decisions.NEED_TITLE,
        name_pattern=check_decisions.NEED_FILENAME,
    )
    assert doc is not None
    check_decisions.check_need(doc, problems, provided=True)
    assert any("Superseded by" in p for p in problems)


# --- the one form of a credential variable (CREDENTIALS.md, DEC-0018) ---------------------------


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE", True),
        ("TAKTUS_DATABASE_URL_FILE", True),
        ("POSTGRES_PASSWORD_FILE", True),
        ("TAKTUS_CREDENTIALS_FILE", False),
        ("TAKTUS_CREDENTIAL__FILE", False),
        ("TAKTUS_MODEL_KEY_FILE", False),
        ("CODING_AGENT_API_KEY_FILE", False),
    ],
)
def test_every_credential_variable_has_the_one_form(name: str, ok: bool) -> None:
    keys = {"database.url", "otlp.headers"}
    assert (check_decisions.variable_form(name, keys) is None) is ok


def test_the_repository_reads_no_variable_of_another_form() -> None:
    text = (ROOT / "CREDENTIALS.md").read_text(encoding="utf-8")
    keys = set(check_decisions.CONFIGURATION_KEY.findall(text))
    wrong = {
        name: why
        for name in check_decisions.code_credential_variables()
        if (why := check_decisions.variable_form(name, keys)) is not None
    }
    assert wrong == {}


# --- the acceptance rate counts what was asked before it was answered (DEC-0042) ----------------


def test_a_record_written_after_the_answer_and_a_mode_4_answer_are_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def record(number: int, answer: str, header: str = "") -> None:
        (tmp_path / f"DEC-{number:04d}-x.md").write_text(
            f"# DEC-{number:04d} — x\n\n**Category:** NON-BLOCKING\n{header}\n"
            "### Option A — one (recommended)\n\n### Option B — two\n\n"
            f"## Outcome\n\n**Answer:** {answer}\n",
            encoding="utf-8",
        )

    record(1, "Option A.")
    record(2, "Option B.")
    record(3, "Option B.")
    record(4, "Option A.", "**Written after the answer:** the owner had answered first.\n")
    record(5, "Option A.", "**Mode entry:** M4.1\n")
    for number in range(1, 21):
        (tmp_path / f"NTC-{number:04d}-z.md").write_text(
            f"# NTC-{number:04d} — z\n\n**Kind:** unlisted\n", encoding="utf-8"
        )
    monkeypatch.setattr(check_status, "REGISTER", tmp_path)
    line = check_status.acceptance()
    assert (
        "of 3 request(s) asked before they were answered, 1 took the recommended option (33 %)"
        in line
    )
    assert "2 written after the answer or of mode 4, left out" in line
    assert (
        "20 decided under the reversed default, the override rate goes to the owner at 40" in line
    )
