# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check the decision register under docs/decisions/ (ADR-0017).

Runs as `make gate-decisions`. Standard library only, so `uv run tools/check_decisions.py` and
`python3 tools/check_decisions.py` both work without the project installed.

Checks:

1. every open request under docs/decisions/open/ has the header, the seven sections in order,
   no empty section, no placeholder, at least two options with exactly one recommended;
2. every record under docs/decisions/ has the same shape plus an Outcome with a date and an
   answer (or, for a DEFECT, what it now says; for a NOTE, why it is a note);
3. a number is used once, and never both under open/ and as a record;
4. every record is listed in docs/decisions/README.md;
4a. every notice (NTC-NNNN, a mode-2 record, ADR-0017 §2a) has its header — a mode-2 entry of
   anchors.taktus.md that exists, a date, the pull request — the four sections in order, no
   placeholder, and is listed in the index; a notice under M2.3 (a gate weakened or removed)
   additionally carries the section "Why the gate had no value", which names the gate;
5. with --pr-body: the "Decisions required" section of a pull request description is either
   "None" or a list of DEC lines, every named decision has an open file with the same category,
   and every BLOCKING open file is named;
6. with --draft false: no BLOCKING decision is open — a pull request with a BLOCKING decision
   stays a draft;
7. with --forbid-open-blocking (push to main): no BLOCKING file is under open/ at all.

A register with nothing in it reports green and says so.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "decisions"
OPEN = REGISTER / "open"
INDEX = REGISTER / "README.md"
ANCHORS = REGISTER / "anchors.taktus.md"

SECTIONS = [
    "1. What this is about",
    "2. Why you are being asked",
    "3. What you must decide",
    "4. What you need to know to decide",
    "5. Options",
    "6. What is blocked",
    "7. How to answer",
]
OUTCOME = "Outcome"
DECISION_CATEGORIES = {"BLOCKING", "NON-BLOCKING"}
CATEGORIES = DECISION_CATEGORIES | {"DEFECT", "NOTE"}
OUTCOME_FIELDS: dict[str, list[str]] = {
    "BLOCKING": ["Decided", "Answer", "Reasoning given", "Recorded in"],
    "NON-BLOCKING": ["Decided", "Answer", "Reasoning given", "Recorded in"],
    "DEFECT": [
        "Corrected",
        "What was wrong",
        "Why it was wrong",
        "What it now says",
        "What changed in substance",
        "Recorded in",
    ],
    "NOTE": ["Recorded", "Why this is a note", "Recorded in"],
}
DATE_FIELDS = {"Needed by", "Decided", "Corrected", "Recorded"}

FILENAME = re.compile(r"^DEC-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
TITLE = re.compile(r"^# DEC-(\d{4}) — (.+)$")

# Notices: the record of a mode-2 decision (ADR-0017 §2a). Section 5 exists exactly for a
# weakened gate, entry M2.3 of anchors.taktus.md.
NOTICE_SECTIONS = [
    "1. What was decided",
    "2. The evidence",
    "3. What was considered",
    "4. Which entry permits it",
]
GATE_SECTION = "5. Why the gate had no value"
GATE_ENTRY = "M2.3"
NOTICE_FILENAME = re.compile(r"^NTC-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
NOTICE_TITLE = re.compile(r"^# NTC-(\d{4}) — (.+)$")
MODE_ENTRY = re.compile(r"^M2\.\d+$")
ENTRY_ROW = re.compile(r"^\| (M[1-4]\.\d+) \|", re.MULTILINE)
GATE_NAME = re.compile(r"`make gate-[a-z-]+`|`tests/[a-z_/.-]+`|`make test`|`make lint`")
FIELD = re.compile(r"^\*\*([A-Za-z ]+):\*\*\s*(.*)$")
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME|XXX)\b|…")
OPTION = re.compile(r"^### Option [A-Z] — ")
RECOMMENDED = re.compile(r"^### Option [A-Z] — .*\(recommended\)\s*$")
DEC_REF = re.compile(r"\bDEC-(\d{4})\b")
ISSUE_REF = re.compile(r"#\d+\b")

type Check = Callable[[Document, list[str]], None]


@dataclass
class Report:
    passed: int = 0
    failures: list[str] = field(default_factory=list)

    def ok(self, what: str) -> None:
        self.passed += 1
        print(f"  ok   {what}")

    def fail(self, what: str, why: str) -> None:
        self.failures.append(f"{what}: {why}")
        print(f"  FAIL {what}\n       {why}")


@dataclass
class Document:
    path: Path
    number: str
    title: str
    fields: dict[str, str]
    sections: dict[str, str]

    @property
    def category(self) -> str:
        return self.fields.get("Category", "")

    @property
    def rel(self) -> str:
        return str(self.path.relative_to(ROOT))


# --- parsing -------------------------------------------------------------------------------------


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def strip_code(text: str) -> str:
    """Placeholders are looked for in prose only: a `<family>` inside code is content."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def parse(
    path: Path,
    *,
    prefix: str = "DEC",
    title_pattern: re.Pattern[str] = TITLE,
    name_pattern: re.Pattern[str] = FILENAME,
) -> tuple[Document | None, list[str]]:
    problems: list[str] = []
    text = strip_comments(path.read_text(encoding="utf-8"))
    lines = text.splitlines()
    match = title_pattern.match(lines[0]) if lines else None
    if match is None:
        return None, [f"first line is not `# {prefix}-NNNN — Title`"]
    number, title = match.groups()
    name = name_pattern.match(path.name)
    if name is None:
        problems.append(f"file name is not {prefix}-NNNN-<slug>.md with a lowercase slug")
    elif name.group(1) != number:
        problems.append(f"file name says {prefix}-{name.group(1)}, title says {prefix}-{number}")

    fields: dict[str, str] = {}
    body_start = 1
    for index, line in enumerate(lines[1:], start=1):
        if line.startswith("## "):
            body_start = index
            break
        if field_match := FIELD.match(line):
            fields[field_match.group(1)] = field_match.group(2).strip()
    else:
        body_start = len(lines)

    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in lines[body_start:]:
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        else:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return Document(path, number, title.strip(), fields, sections), problems


# --- shape ---------------------------------------------------------------------------------------


def valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def check_fields(doc: Document, required: list[str], problems: list[str]) -> None:
    for name in required:
        if not doc.fields.get(name):
            problems.append(f"header field `**{name}:**` is missing or empty")
    for name, value in doc.fields.items():
        if name in DATE_FIELDS and value and not valid_date(value):
            problems.append(f"`**{name}:**` is not a date of the form YYYY-MM-DD: {value!r}")
        if PLACEHOLDER.search(strip_code(value)):
            problems.append(f"`**{name}:**` keeps a placeholder: {value!r}")


def check_sections(doc: Document, problems: list[str]) -> None:
    present = [name for name in doc.sections if name != OUTCOME]
    if present != SECTIONS:
        missing = [name for name in SECTIONS if name not in present]
        unexpected = [name for name in present if name not in SECTIONS]
        if missing:
            problems.append("missing section(s): " + ", ".join(f"`## {m}`" for m in missing))
        if unexpected:
            problems.append("unexpected section(s): " + ", ".join(f"`## {u}`" for u in unexpected))
        if not missing and not unexpected:
            problems.append("sections are out of order")
    for name in SECTIONS:
        body = doc.sections.get(name, "")
        if not body:
            if name in doc.sections:
                problems.append(f"`## {name}` is empty")
            continue
        if found := PLACEHOLDER.search(strip_code(body)):
            problems.append(f"`## {name}` keeps a placeholder: {found.group(0)!r}")


def check_options(doc: Document, problems: list[str]) -> None:
    body = doc.sections.get(SECTIONS[4], "")
    options = [line for line in body.splitlines() if OPTION.match(line)]
    recommended = [line for line in options if RECOMMENDED.match(line)]
    if len(options) < 2:
        problems.append(
            f"`## {SECTIONS[4]}` has {len(options)} option heading(s), needs two or three"
        )
    elif len(options) > 3:
        problems.append(f"`## {SECTIONS[4]}` has {len(options)} options, at most three")
    if len(recommended) != 1:
        problems.append(
            f"`## {SECTIONS[4]}` marks {len(recommended)} option(s) recommended, needs one"
        )


def outcome_fields(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        if match := FIELD.match(line):
            found[match.group(1)] = match.group(2).strip()
    return found


def check_open(doc: Document, problems: list[str]) -> None:
    if doc.category not in DECISION_CATEGORIES:
        problems.append(
            f"`**Category:**` must be BLOCKING or NON-BLOCKING under open/, found {doc.category!r}"
        )
    required = ["Category", "Raised in", "Issue", "Needed by"]
    if doc.category == "NON-BLOCKING":
        required.append("Provisional answer")
    elif doc.category == "BLOCKING" and "Provisional answer" in doc.fields:
        problems.append(
            "a BLOCKING request carries no provisional answer; if one exists, it is NON-BLOCKING"
        )
    check_fields(doc, required, problems)
    if not ISSUE_REF.search(doc.fields.get("Issue", "")):
        problems.append("`**Issue:**` names no issue (#N)")
    check_sections(doc, problems)
    check_options(doc, problems)
    if OUTCOME in doc.sections:
        problems.append("an open request has no `## Outcome`; move the file to docs/decisions/")


def check_record(doc: Document, problems: list[str]) -> None:
    if doc.category not in CATEGORIES:
        problems.append(
            f"`**Category:**` must be one of {sorted(CATEGORIES)}, found {doc.category!r}"
        )
    check_fields(doc, ["Category", "Raised in"], problems)
    check_sections(doc, problems)
    if doc.category in DECISION_CATEGORIES:
        check_options(doc, problems)
    outcome = doc.sections.get(OUTCOME)
    if outcome is None:
        problems.append("`## Outcome` is missing: a record carries the answer and its date")
        return
    found = outcome_fields(outcome)
    for name in OUTCOME_FIELDS.get(doc.category, []):
        value = found.get(name, "")
        if not value:
            problems.append(f"`## Outcome` lacks `**{name}:**`")
        elif name in DATE_FIELDS and not valid_date(value):
            problems.append(f"`**{name}:**` is not a date of the form YYYY-MM-DD: {value!r}")
    if PLACEHOLDER.search(strip_code(outcome)):
        problems.append("`## Outcome` keeps a placeholder")


# --- notices -------------------------------------------------------------------------------------


def mode_two_entries() -> set[str]:
    """The entry identifiers the tenant's anchor page defines; a notice cites one of mode 2."""
    if not ANCHORS.exists():
        return set()
    return set(ENTRY_ROW.findall(ANCHORS.read_text(encoding="utf-8")))


def check_notice(doc: Document, problems: list[str], entries: set[str]) -> None:
    check_fields(doc, ["Mode entry", "Decided", "Raised in"], problems)
    entry = doc.fields.get("Mode entry", "")
    if entry and not MODE_ENTRY.match(entry):
        problems.append(f"`**Mode entry:**` is not a mode-2 entry (M2.N): {entry!r}")
    elif entry and entries and entry not in entries:
        problems.append(f"`**Mode entry:**` {entry} is not an entry of {ANCHORS.name}")
    present = list(doc.sections)
    expected = NOTICE_SECTIONS + ([GATE_SECTION] if entry == GATE_ENTRY else [])
    if present != expected:
        missing = [name for name in expected if name not in present]
        unexpected = [name for name in present if name not in expected]
        if missing:
            problems.append("missing section(s): " + ", ".join(f"`## {m}`" for m in missing))
        if unexpected:
            problems.append("unexpected section(s): " + ", ".join(f"`## {u}`" for u in unexpected))
        if not missing and not unexpected:
            problems.append("sections are out of order")
    for name, body in doc.sections.items():
        if not body:
            problems.append(f"`## {name}` is empty")
        elif found := PLACEHOLDER.search(strip_code(body)):
            problems.append(f"`## {name}` keeps a placeholder: {found.group(0)!r}")
    if entry == GATE_ENTRY and (body := doc.sections.get(GATE_SECTION)):
        if GATE_NAME.search(body) is None:
            problems.append(
                f"`## {GATE_SECTION}` names no gate (`make gate-<name>`, `make test`, `make lint` "
                "or a `tests/<path>`)"
            )
        if len(body) < 300:
            problems.append(
                f"`## {GATE_SECTION}` is too short to be a demonstration: state what the gate "
                "looked at, what it would have caught, and the evidence it caught nothing"
            )
    if entry and entry != GATE_ENTRY and GATE_SECTION in doc.sections:
        problems.append(f"`## {GATE_SECTION}` belongs to {GATE_ENTRY} only")


def check_notices(report: Report) -> list[Document]:
    print("notices")
    entries = mode_two_entries()
    notices: list[Document] = []
    seen: dict[str, str] = {}
    for path in sorted(REGISTER.glob("NTC-*.md")):
        doc, problems = parse(
            path, prefix="NTC", title_pattern=NOTICE_TITLE, name_pattern=NOTICE_FILENAME
        )
        rel = str(path.relative_to(ROOT))
        if doc is not None:
            check_notice(doc, problems, entries)
            if doc.number in seen:
                problems.append(f"NTC-{doc.number} is also {seen[doc.number]}")
            seen[doc.number] = rel
            notices.append(doc)
        if problems:
            report.fail(rel, "; ".join(problems))
        else:
            report.ok(rel)
    if not notices:
        report.ok("no notices yet")
        return notices
    index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    unlisted = [doc for doc in notices if doc.path.name not in index]
    if unlisted:
        report.fail(
            str(INDEX.relative_to(ROOT)),
            "not listed: " + ", ".join(doc.path.name for doc in unlisted),
        )
    else:
        report.ok(f"{INDEX.relative_to(ROOT)} lists every notice")
    return notices


def load(directory: Path, report: Report, checker: Check) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(directory.glob("DEC-*.md")):
        doc, problems = parse(path)
        if doc is not None:
            checker(doc, problems)
            docs.append(doc)
        rel = str(path.relative_to(ROOT))
        if problems:
            report.fail(rel, "; ".join(problems))
        else:
            report.ok(rel)
    return docs


# --- register ------------------------------------------------------------------------------------


def check_register(report: Report) -> tuple[list[Document], list[Document]]:
    print("open requests")
    open_docs = load(OPEN, report, check_open) if OPEN.is_dir() else []
    if not open_docs:
        report.ok("no open requests")
    print("records")
    records = load(REGISTER, report, check_record)
    if not records:
        report.ok("no records yet")

    seen: dict[str, str] = {}
    for doc in [*open_docs, *records]:
        if doc.number in seen:
            report.fail(doc.rel, f"DEC-{doc.number} is also {seen[doc.number]}")
        seen[doc.number] = doc.rel
    open_numbers = {doc.number for doc in open_docs}
    for doc in records:
        if doc.number in open_numbers:
            report.fail(doc.rel, "its record exists, but the file is still under open/")

    if records:
        index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        unlisted = [doc for doc in records if doc.path.name not in index]
        if unlisted:
            report.fail(
                str(INDEX.relative_to(ROOT)),
                "not listed: " + ", ".join(doc.path.name for doc in unlisted),
            )
        else:
            report.ok(f"{INDEX.relative_to(ROOT)} lists every record")
    return open_docs, records


# --- pull request --------------------------------------------------------------------------------


def decisions_section(body: str) -> str | None:
    """The text under `## Decisions required` without comments; None if the heading is absent."""
    lines = strip_comments(body).splitlines()
    inside = False
    collected: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lower() == "decisions required"
            continue
        if inside:
            collected.append(line)
    return "\n".join(collected).strip() if inside else None


def check_pull_request(
    body: str, draft: bool | None, open_docs: list[Document], report: Report
) -> None:
    print("pull request")
    section = decisions_section(body)
    if section is None:
        report.fail("description", "no `## Decisions required` section (see the template)")
        return
    named: dict[str, str] = {}
    if section.lower() != "none":
        for line in (line.strip() for line in section.splitlines() if line.strip()):
            ref = DEC_REF.search(line)
            category = next((c for c in ("NON-BLOCKING", "BLOCKING") if c in line), None)
            if ref is None or category is None or not ISSUE_REF.search(line):
                report.fail(
                    "description",
                    f"not a decision line (`DEC-NNNN — title — CATEGORY — #issue`): {line!r}",
                )
                continue
            named[ref.group(1)] = category
    by_number = {doc.number: doc for doc in open_docs}
    for number, category in named.items():
        doc = by_number.get(number)
        if doc is None:
            report.fail(f"DEC-{number}", "named in the description but has no file under open/")
        elif doc.category != category:
            report.fail(
                f"DEC-{number}", f"description says {category}, the file says {doc.category}"
            )
        else:
            report.ok(f"DEC-{number} ({category}) has {doc.rel}")
    for doc in open_docs:
        if doc.category == "BLOCKING" and doc.number not in named:
            report.fail(doc.rel, "BLOCKING but not named under `## Decisions required`")
    blocking = [doc for doc in open_docs if doc.category == "BLOCKING"]
    if draft is False and blocking:
        report.fail(
            "draft",
            "a pull request with a BLOCKING decision stays a draft until the answer is recorded: "
            + ", ".join(f"DEC-{doc.number}" for doc in blocking),
        )
    elif not named:
        report.ok("no decisions required")
    elif draft is None:
        report.ok("draft state not given; not checked")
    else:
        report.ok("draft state matches the decisions named")


# --- main ----------------------------------------------------------------------------------------


def parse_bool(value: str) -> bool:
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"expected true or false, got {value!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pr-body", type=Path, help="file holding the pull request description")
    parser.add_argument("--draft", type=parse_bool, help="github.event.pull_request.draft")
    parser.add_argument(
        "--forbid-open-blocking",
        action="store_true",
        help="fail on any BLOCKING file under open/ (use on the main branch)",
    )
    args = parser.parse_args(argv)

    report = Report()
    open_docs, _records = check_register(report)
    check_notices(report)
    if args.pr_body is not None:
        check_pull_request(args.pr_body.read_text(encoding="utf-8"), args.draft, open_docs, report)
    if args.forbid_open_blocking:
        for doc in open_docs:
            if doc.category == "BLOCKING":
                report.fail(
                    doc.rel, "BLOCKING request on the main branch; it was merged unanswered"
                )
    print()
    if report.failures:
        print(f"{report.passed} passed, {len(report.failures)} failed")
        return 1
    print(f"{report.passed} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
