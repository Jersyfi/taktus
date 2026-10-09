# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check the decision register under docs/decisions/ (ADR-0017).

Runs as `make gate-decisions`. Standard library only, so `uv run tools/check_decisions.py` and
`python3 tools/check_decisions.py` both work without the project installed.

Checks:

1. every open request under docs/decisions/open/ has the header, the seven sections in order,
   no empty section, no placeholder, at least two options with exactly one recommended — none,
   where `**Mode entry:**` names a mode-4 entry, the owner's own question (DEC-0045); from
   DEC-0039 on, its section 2 names `**Sources checked:**` — the vision, the ADRs, the anchor
   pages, the register — and why none of them answers it (the derivability test);
2. every record under docs/decisions/ has the same shape plus an Outcome with a date and an
   answer (or, for a DEFECT, what it now says; for a NOTE, why it is a note);
3. a number is used once, and never both under open/ and as a record;
4. every record is listed in docs/decisions/README.md, in its own table — a decision under
   Decisions, a notice under Notices, a provided need under Needs;
4a. every notice (NTC-NNNN, a mode-2 record, ADR-0017 §2a) has its header — a mode-2 entry of
   anchors.taktus.md that exists, the kind that entry names there, a date, the pull request —
   the four sections in order, no placeholder, and is listed in the index; a notice of kind
   gate-weakened (a gate weakened or removed, entry M2.3) additionally carries the section
   "Why the gate had no value", which names the gate; a notice of kind unlisted (a situation that
   fit no entry, decided in the direction of the vision, entry M2.6) carries the section "The
   entry it proposes", which names one; a notice of kind unlisted or restoration (a use case
   brought up to the owner's own definition, entry M2.7) states `**How it follows:**` from its
   source (DEC-0040) — the gate sees that the statement is there, review sees whether it holds;
   a notice a later decision overrode says so in `**Overridden by:** DEC-NNNN`;
4d. after every twenty unlisted notices, a decision request or record carrying
   `**Override review:**` exists — the request that puts the override rate to the owner
   (DEC-0042);
4b. every needs request (NEED-NNNN, something only the owner can provide, ADR-0028) has its
   header — a kind from the vocabulary, the pull request, an issue, a date, the pull request in
   which it became foreseeable — the seven sections in order, no empty section, no placeholder,
   and section 5 says what it must never be; a provided need has an Outcome with the date it
   was provided, how it was confirmed and where it was recorded, and is listed in the index; a
   need closed because another took its place says so in `**Superseded by:**`;
4c. every credential the software reads is covered: every row of CREDENTIALS.md names the needs
   request under which the owner provides the parameter, or `none` with the reason; every
   needs request a row names has a file; every `<NAME>_FILE` variable the code names is
   described in CREDENTIALS.md — so that a pull request cannot build something whose real use
   depends on a credential nobody was asked for; and every such variable has the one form
   (CREDENTIALS.md, DEC-0018): `TAKTUS_CREDENTIAL_<NAME>_FILE` for a credential,
   `TAKTUS_<KEY>_FILE` for a configuration key the register names, or a variable of an image
   Taktus does not build, listed in `FOREIGN_VARIABLES` with its reason;
4e. across the repository: every `NEED-NNNN` names a need that has a file; outside the register,
   a need named is open or provided, never superseded — a reference to a superseded need points
   at something nobody will provide; and every `TODO(owner)` names an open need or decision
   request, so that an action left to the owner is a record with an issue, not a comment;
5. with --pr-body (and --author, the description's author): the "Decisions required" section of a
   pull request description is either "None" or a list of DEC lines, every named decision has an
   open file with the same category, and every BLOCKING open file is named;
5a. with --pr-body: the description carries, in this order, "What this is about", "What was
   done", "Why this way" and "What to check", none empty and none a placeholder — so that a
   reviewer who has not read the diff can act on it (ADR-0017 §7). The gate sees that the four
   are there and filled, not that they are true or readable without the diff;
6. with --draft false: no BLOCKING decision is open — a pull request with a BLOCKING decision
   stays a draft;
7. with --forbid-open-blocking (push to main): no BLOCKING file is under open/ at all.

Checks 5 and 5a are not asked of a description a dependency bot wrote (`DEPENDENCY_BOTS`,
NTC-0013): it carries its own explanation of what it changes. Every other check still runs.

`**Needed by:**` is a date, or — for a question with no date of its own, such as a mode-4 question
due before a milestone — `before` and what it must precede. `**Written after the answer:**` on a
record says that the request was written after the owner had answered; `make status` leaves it out
of the acceptance rate (DEC-0042).

A register with nothing in it reports green and says so. The last line is the duration.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
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
DATE_FIELDS = {"Needed by", "Decided", "Corrected", "Recorded", "Provided"}
BEFORE = re.compile(r"^before \S")
"""`**Needed by:**` of a question with no date of its own: `before` what it must precede."""

FILENAME = re.compile(r"^DEC-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
TITLE = re.compile(r"^# DEC-(\d{4}) — (.+)$")

# Notices: the record of a mode-2 decision (ADR-0017 §2a). Every notice carries the kind its
# entry names on the tenant's anchor page (DEC-0014); section 5 exists exactly for the kind
# gate-weakened, a weakened or removed gate.
NOTICE_SECTIONS = [
    "1. What was decided",
    "2. The evidence",
    "3. What was considered",
    "4. Which entry permits it",
]
GATE_SECTION = "5. Why the gate had no value"
GATE_KIND = "gate-weakened"
UNLISTED_SECTION = "5. The entry it proposes"
UNLISTED_KIND = "unlisted"
"""A situation that fit no entry, decided in the direction of the vision (DEC-0039): the notice
proposes the entry that would have covered it."""
FIFTH_SECTION = {GATE_KIND: GATE_SECTION, UNLISTED_KIND: UNLISTED_SECTION}
RESTORATION_KIND = "restoration"
"""A use case brought up to what the vision and the owner's definition already require (DEC-0041,
entry M2.7)."""
FOLLOWS = "How it follows"
FOLLOWS_KINDS = {UNLISTED_KIND, RESTORATION_KIND}
"""The kinds whose notice decides by a source, and so states how the decision follows from it
(DEC-0040). The gate sees that the statement is there; whether it holds is for review."""
REVIEW_FIELD = "Override review"
REVIEW_EVERY = 20
"""After every twenty unlisted notices a request puts the override rate to the owner (DEC-0042)."""
SOURCES = re.compile(r"\*\*Sources checked:\*\*(.+)", re.DOTALL)
SOURCE_PLACES = {
    "the vision": re.compile(r"docs/vision|\bvision\b", re.IGNORECASE),
    "the ADRs": re.compile(r"\bADR-\d{4}|\bADRs?\b"),
    "the anchor pages": re.compile(r"anchors(\.taktus)?\.md|\banchor"),
    "the register": re.compile(r"\bregister\b|\bDEC-\d{4}|\bNTC-\d{4}"),
}
DERIVABILITY_FROM = 39
"""The first request number the derivability test applies to (DEC-0039): the requests raised
before it are the owner's to read as they are."""
OVERRIDDEN = re.compile(r"^DEC-\d{4}\b")
NOTICE_FILENAME = re.compile(r"^NTC-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
NOTICE_TITLE = re.compile(r"^# NTC-(\d{4}) — (.+)$")
MODE_ENTRY = re.compile(r"^M2\.\d+$")
ENTRY_ROW = re.compile(r"^\| (M[1-4]\.\d+) \|", re.MULTILINE)
KIND = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
KIND_CELL = re.compile(r"^`([a-z]+(?:-[a-z]+)*)`$")
GATE_NAME = re.compile(r"`make gate-[a-z-]+`|`tests/[a-z_/.-]+`|`make test`|`make lint`")
# Needs requests: something only the owner can provide (ADR-0028). The shape is seven sections
# with the steps, and section 5 states where the value goes instead of a chat or a commit.
NEED_SECTIONS = [
    "1. What is needed",
    "2. Why",
    "3. By when",
    "4. How to provide it",
    "5. What it must never be",
    "6. What happens next",
    "7. How to confirm",
]
NEED_KINDS = {"credential", "account", "access", "purchase", "action", "information"}
NEED_OUTCOME_FIELDS = ["Provided", "Confirmed by", "Recorded in"]
NEED_FILENAME = re.compile(r"^NEED-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
NEED_TITLE = re.compile(r"^# NEED-(\d{4}) — (.+)$")
NEED_REF = re.compile(r"\bNEED-(\d{4})\b")
NEVER = re.compile(r"\bnever\b", re.IGNORECASE)
SUPERSEDED = re.compile(r"\bsuperseded\b", re.IGNORECASE)
SUPERSEDED_FIELD = "Superseded by"
TODO_OWNER = re.compile(r"TODO\(owner\)")
REFERENCE_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".json", ".toml", ".txt", ".example"}
REFERENCE_EXEMPT = ("tools/check_decisions.py", "tests/tools/")
"""Where an identifier is an example, not a reference: the gate itself and its tests."""

# Credential coverage (ADR-0028 §2): the register of parameters, its column naming the need,
# and the directories whose code names a credential file variable.
CREDENTIALS = ROOT / "CREDENTIALS.md"
NEEDS_COLUMN = "Needs request"
CREDENTIAL_VARIABLE = re.compile(r"\b[A-Z][A-Z0-9_]+_FILE\b")
CREDENTIAL_PREFIX = re.compile(r"^TAKTUS_CREDENTIAL_([A-Z0-9_]+)_FILE$")
CODE_DIRECTORIES = ("src", "workers", "tools", "deploy", "blueprints")
CODE_SUFFIXES = {".py", ".sh", ".yml", ".yaml"}
CODE_FILES = (".env.example",)
CONFIGURATION_KEY = re.compile(r"configuration key `([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)`")
FOREIGN_VARIABLES = {
    "POSTGRES_PASSWORD_FILE": "the database image's own variable for its superuser password, "
    "which `deploy/docker/compose.yml` hands it; the image is not Taktus's, so the name is not",
}
"""`<NAME>_FILE` variables named by an image Taktus does not build. Their form is that image's;
every other one is Taktus's and has Taktus's form."""

FIELD = re.compile(r"^\*\*([A-Za-z ]+):\*\*\s*(.*)$")
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME|XXX)\b|…")
OPTION = re.compile(r"^### Option [A-Z] — ")
RECOMMENDED = re.compile(r"^### Option [A-Z] — .*\(recommended\)\s*$")
DEC_REF = re.compile(r"\bDEC-(\d{4})\b")
OWNERS_OWN = re.compile(r"^M4\.\d+$")
"""A mode-4 entry: the owner's own question, asked with data and no recommendation (DEC-0045)."""
# What every pull request description states without assuming the reader has read the diff
# (ADR-0017 §7): what it is about, what was done, why that way, what the reviewer should check.
DESCRIPTION = ["What this is about", "What was done", "Why this way", "What to check"]
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


def index_section(heading: str) -> str:
    """The part of the register's index under `## <heading>`: a record is listed in its own
    table — a notice under Notices, a need under Needs, a decision under Decisions — so that the
    index reads by kind and a row filed in the wrong table is found."""
    text = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    found = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return found[1] if found else ""


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
        undated = name == "Needed by" and BEFORE.match(value)
        if name in DATE_FIELDS and value and not valid_date(value) and not undated:
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
    if OWNERS_OWN.match(doc.fields.get("Mode entry", "")):
        if len(options) < 2:
            problems.append(f"`## {SECTIONS[4]}` has {len(options)} option heading(s), needs two")
        if recommended:
            problems.append(
                f"`## {SECTIONS[4]}` recommends an option in a mode-4 request; the question is "
                "the owner's own, and the session supplies data, not a recommendation (DEC-0045)"
            )
        return
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
    check_derivability(doc, problems)
    if OUTCOME in doc.sections:
        problems.append("an open request has no `## Outcome`; move the file to docs/decisions/")


def check_derivability(doc: Document, problems: list[str]) -> None:
    """The derivability test (DEC-0039): a request names, in its section 2, the sources it
    checked — the vision, the ADRs, the anchor pages, the register — and why none answers it."""
    if int(doc.number) < DERIVABILITY_FROM:
        return
    found = SOURCES.search(doc.sections.get(SECTIONS[1], ""))
    if found is None:
        problems.append(
            "section 2 names no `**Sources checked:**`: the vision, the ADRs, the anchor pages "
            "and the register, and why none of them answers the question (DEC-0039)"
        )
        return
    missing = [place for place, pattern in SOURCE_PLACES.items() if not pattern.search(found[1])]
    if missing:
        problems.append("`**Sources checked:**` does not name " + ", ".join(missing))


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


def anchor_entries() -> dict[str, str | None]:
    """The entry identifiers the tenant's anchor page defines, each with the kind its row names
    in a cell of its own (`restructuring`); None where the row names no kind."""
    if not ANCHORS.exists():
        return {}
    entries: dict[str, str | None] = {}
    for line in ANCHORS.read_text(encoding="utf-8").splitlines():
        if (row := ENTRY_ROW.match(line)) is None:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        kinds = [m.group(1) for cell in cells[1:] if (m := KIND_CELL.match(cell))]
        entries[row.group(1)] = kinds[0] if kinds else None
    return entries


def check_notice(doc: Document, problems: list[str], entries: dict[str, str | None]) -> None:
    check_fields(doc, ["Mode entry", "Kind", "Decided", "Raised in"], problems)
    overridden = doc.fields.get("Overridden by")
    if overridden is not None and OVERRIDDEN.match(overridden) is None:
        problems.append(f"`**Overridden by:**` names no decision (DEC-NNNN): {overridden!r}")
    entry = doc.fields.get("Mode entry", "")
    kind = doc.fields.get("Kind", "")
    if entry and not MODE_ENTRY.match(entry):
        problems.append(f"`**Mode entry:**` is not a mode-2 entry (M2.N): {entry!r}")
    elif entry and entries and entry not in entries:
        problems.append(f"`**Mode entry:**` {entry} is not an entry of {ANCHORS.name}")
    if kind and not KIND.match(kind):
        problems.append(f"`**Kind:**` is not a kind (lowercase words joined by `-`): {kind!r}")
    elif kind and entries.get(entry) is not None and kind != entries[entry]:
        problems.append(
            f"`**Kind:**` {kind} is not the kind {ANCHORS.name} names for {entry}: {entries[entry]}"
        )
    elif kind and entry in entries and entries[entry] is None:
        problems.append(f"{ANCHORS.name} names no kind for {entry}; every mode-2 entry has one")
    present = list(doc.sections)
    expected = NOTICE_SECTIONS + ([FIFTH_SECTION[kind]] if kind in FIFTH_SECTION else [])
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
    if kind == GATE_KIND and (gate_body := doc.sections.get(GATE_SECTION)):
        if GATE_NAME.search(gate_body) is None:
            problems.append(
                f"`## {GATE_SECTION}` names no gate (`make gate-<name>`, `make test`, `make lint` "
                "or a `tests/<path>`)"
            )
        if len(gate_body) < 300:
            problems.append(
                f"`## {GATE_SECTION}` is too short to be a demonstration: state what the gate "
                "looked at, what it would have caught, and the evidence it caught nothing"
            )
    if kind and kind != GATE_KIND and GATE_SECTION in doc.sections:
        problems.append(f"`## {GATE_SECTION}` belongs to the kind {GATE_KIND} only")
    if kind in FOLLOWS_KINDS and len(doc.fields.get(FOLLOWS, "")) < 40:
        problems.append(
            f"a notice of kind {kind} decides by a source and states `**{FOLLOWS}:**` — how the "
            "decision follows from it, not only which source was named (DEC-0040)"
        )
    if kind == UNLISTED_KIND and (unlisted_body := doc.sections.get(UNLISTED_SECTION)):
        if re.search(r"\bM[1-4]\.\d+\b", unlisted_body) is None:
            problems.append(
                f"`## {UNLISTED_SECTION}` names no entry (`M<mode>.<n>`) for the anchor page"
            )


def check_notices(report: Report) -> list[Document]:
    print("notices")
    entries = anchor_entries()
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
    index = index_section("Notices")
    unlisted = [doc for doc in notices if doc.path.name not in index]
    if unlisted:
        report.fail(
            str(INDEX.relative_to(ROOT)),
            "not listed under Notices: " + ", ".join(doc.path.name for doc in unlisted),
        )
    else:
        report.ok(f"{INDEX.relative_to(ROOT)} lists every notice under Notices")
    return notices


# --- needs ---------------------------------------------------------------------------------------


def check_need(doc: Document, problems: list[str], *, provided: bool) -> None:
    check_fields(doc, ["Kind", "Raised in", "Issue", "Needed by", "Foreseeable since"], problems)
    kind = doc.fields.get("Kind", "")
    if kind and kind not in NEED_KINDS:
        problems.append(f"`**Kind:**` must be one of {sorted(NEED_KINDS)}, found {kind!r}")
    if not ISSUE_REF.search(doc.fields.get("Issue", "")):
        problems.append("`**Issue:**` names no issue (#N)")
    present = [name for name in doc.sections if name != OUTCOME]
    if present != NEED_SECTIONS:
        missing = [name for name in NEED_SECTIONS if name not in present]
        unexpected = [name for name in present if name not in NEED_SECTIONS]
        if missing:
            problems.append("missing section(s): " + ", ".join(f"`## {m}`" for m in missing))
        if unexpected:
            problems.append("unexpected section(s): " + ", ".join(f"`## {u}`" for u in unexpected))
        if not missing and not unexpected:
            problems.append("sections are out of order")
    for name in NEED_SECTIONS:
        body = doc.sections.get(name, "")
        if not body:
            if name in doc.sections:
                problems.append(f"`## {name}` is empty")
            continue
        if found := PLACEHOLDER.search(strip_code(body)):
            problems.append(f"`## {name}` keeps a placeholder: {found.group(0)!r}")
    never_section = doc.sections.get(NEED_SECTIONS[4], "")
    if never_section and NEVER.search(never_section) is None:
        problems.append(
            f"`## {NEED_SECTIONS[4]}` says nothing the value must never be; the repository is "
            "public and a session never receives a secret value"
        )
    outcome = doc.sections.get(OUTCOME)
    if not provided:
        if outcome is not None:
            problems.append("an open need has no `## Outcome`; move the file to docs/decisions/")
        return
    if outcome is None:
        problems.append("`## Outcome` is missing: a provided need carries the date and the check")
        return
    fields = outcome_fields(outcome)
    replaced_by = fields.get(SUPERSEDED_FIELD)
    if replaced_by is None and SUPERSEDED.search(outcome):
        problems.append(
            f"`## Outcome` says the need was superseded and has no `**{SUPERSEDED_FIELD}:**` "
            "naming what took its place"
        )
    elif replaced_by is not None and not (
        NEED_REF.search(replaced_by) or DEC_REF.search(replaced_by)
    ):
        problems.append(
            f"`**{SUPERSEDED_FIELD}:**` names no NEED-NNNN or DEC-NNNN: {replaced_by!r}"
        )
    for name in NEED_OUTCOME_FIELDS:
        value = fields.get(name, "")
        if not value:
            problems.append(f"`## Outcome` lacks `**{name}:**`")
        elif name in DATE_FIELDS and not valid_date(value):
            problems.append(f"`**{name}:**` is not a date of the form YYYY-MM-DD: {value!r}")
    if PLACEHOLDER.search(strip_code(outcome)):
        problems.append("`## Outcome` keeps a placeholder")


def superseded(doc: Document) -> bool:
    """A need closed because another took its place: nobody will provide it."""
    return SUPERSEDED_FIELD in outcome_fields(doc.sections.get(OUTCOME, ""))


def load_needs(directory: Path, report: Report, *, provided: bool) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(directory.glob("NEED-*.md")):
        doc, problems = parse(
            path, prefix="NEED", title_pattern=NEED_TITLE, name_pattern=NEED_FILENAME
        )
        if doc is not None:
            check_need(doc, problems, provided=provided)
            docs.append(doc)
        rel = str(path.relative_to(ROOT))
        if problems:
            report.fail(rel, "; ".join(problems))
        else:
            report.ok(rel)
    return docs


def check_needs(report: Report) -> tuple[list[Document], list[Document]]:
    print("needs")
    open_needs = load_needs(OPEN, report, provided=False) if OPEN.is_dir() else []
    provided = load_needs(REGISTER, report, provided=True)
    if not open_needs and not provided:
        report.ok("no needs yet")
    seen: dict[str, str] = {}
    for doc in [*open_needs, *provided]:
        if doc.number in seen:
            report.fail(doc.rel, f"NEED-{doc.number} is also {seen[doc.number]}")
        seen[doc.number] = doc.rel
    if provided:
        index = index_section("Needs")
        unlisted = [doc for doc in provided if doc.path.name not in index]
        if unlisted:
            report.fail(
                str(INDEX.relative_to(ROOT)),
                "not listed under Needs: " + ", ".join(doc.path.name for doc in unlisted),
            )
        else:
            report.ok(f"{INDEX.relative_to(ROOT)} lists every provided need under Needs")
    return open_needs, provided


def credential_rows(text: str) -> tuple[list[str], list[list[str]]]:
    """The header and the rows of the parameter table in CREDENTIALS.md; cells stripped."""
    header: list[str] = []
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not header:
            if "Parameter" in cells:
                header = cells
            continue
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if cells and cells[0].startswith("**"):
            rows.append(cells)
    return header, rows


def code_credential_variables() -> dict[str, str]:
    """Every `<NAME>_FILE` variable the code names, with the first file naming it."""
    found: dict[str, str] = {}
    for directory in CODE_DIRECTORIES:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in CODE_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in CREDENTIAL_VARIABLE.findall(text):
                found.setdefault(name, str(path.relative_to(ROOT)))
    for name in CODE_FILES:
        if (path := ROOT / name).is_file():
            for variable in CREDENTIAL_VARIABLE.findall(path.read_text(encoding="utf-8")):
                found.setdefault(variable, name)
    return found


def variable_form(name: str, keys: set[str]) -> str | None:
    """Why a `<NAME>_FILE` variable does not have the one form (CREDENTIALS.md, DEC-0018); None
    when it has it."""
    if name.startswith("TAKTUS_CREDENTIAL"):
        if CREDENTIAL_PREFIX.match(name) and not name.startswith("TAKTUS_CREDENTIAL__"):
            return None
        return "a credential's variable is `TAKTUS_CREDENTIAL_<NAME>_FILE`"
    if name.startswith("TAKTUS_"):
        if name in {f"TAKTUS_{key.upper().replace('.', '_')}_FILE" for key in keys}:
            return None
        return (
            "a secret's variable is `TAKTUS_<KEY>_FILE` for a configuration key this register "
            "names, and no row names the key this variable would stand for"
        )
    if name in FOREIGN_VARIABLES:
        return None
    return (
        "not Taktus's form (`TAKTUS_CREDENTIAL_<NAME>_FILE`, `TAKTUS_<KEY>_FILE`) and not an "
        "image's own variable listed in FOREIGN_VARIABLES"
    )


def check_credentials(report: Report, needs: list[Document]) -> None:
    """Every credential is covered by a need or a stated reason (ADR-0028 §2)."""
    print("credentials")
    rel = str(CREDENTIALS.relative_to(ROOT))
    if not CREDENTIALS.exists():
        report.fail(rel, "missing; every credential is a parameter described there")
        return
    text = CREDENTIALS.read_text(encoding="utf-8")
    header, rows = credential_rows(text)
    if NEEDS_COLUMN not in header:
        report.fail(rel, f"the parameter table has no column `{NEEDS_COLUMN}`")
        return
    column = header.index(NEEDS_COLUMN)
    known = {doc.number for doc in needs}
    for cells in rows:
        parameter = cells[0].strip("*")
        cell = cells[column] if column < len(cells) else ""
        refs = NEED_REF.findall(cell)
        if refs:
            absent = [f"NEED-{n}" for n in refs if n not in known]
            if absent:
                report.fail(rel, f"{parameter}: names {', '.join(absent)}, which has no file")
            else:
                report.ok(f"{parameter}: " + ", ".join(f"NEED-{n}" for n in refs))
        elif cell.lower().startswith("none") and len(cell) > 8:
            report.ok(f"{parameter}: none, with a reason")
        else:
            report.fail(
                rel,
                f"{parameter}: `{NEEDS_COLUMN}` names no NEED-NNNN and gives no reason "
                "(`none — <why nobody provides it>`)",
            )
    keys = set(CONFIGURATION_KEY.findall(text))
    for name, where in sorted(code_credential_variables().items()):
        covered = name in text
        if not covered and (match := CREDENTIAL_PREFIX.match(name)):
            covered = match.group(1) in text
        if (why := variable_form(name, keys)) is not None:
            report.fail(rel, f"{name}, read by {where}: {why}")
        elif covered:
            report.ok(f"{name} ({where}) is described and has the one form")
        else:
            report.fail(
                rel,
                f"{name} is read by {where} and not described here; add its parameter row, "
                "naming the needs request under which the owner provides it",
            )


def check_override_review(
    report: Report, notices: list[Document], decisions: list[Document]
) -> None:
    """After every twenty unlisted notices, a request puts the override rate to the owner."""
    print("override review")
    unlisted = sum(1 for doc in notices if doc.fields.get("Kind") == UNLISTED_KIND)
    due = unlisted // REVIEW_EVERY
    reviews = [doc for doc in decisions if doc.fields.get(REVIEW_FIELD)]
    if len(reviews) >= due:
        report.ok(
            f"{unlisted} unlisted notice(s); {len(reviews)} override review(s), {due} due — the "
            f"next after {(due + 1) * REVIEW_EVERY}"
        )
    else:
        report.fail(
            "register",
            f"{unlisted} unlisted notices and {len(reviews)} override review(s): a decision "
            f"request carrying `**{REVIEW_FIELD}:**` and the rate at which the owner overrode "
            f"them is due after every {REVIEW_EVERY} (DEC-0042)",
        )


def repository_files() -> list[Path]:
    """The tracked text files a reference can sit in; the working tree when git is absent."""
    try:
        # A fixed executable and arguments assembled here, not from input: nothing untrusted.
        listed = subprocess.run(
            ["git", "ls-files"],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        paths = [ROOT / name for name in listed]
    except (OSError, subprocess.CalledProcessError):
        paths = [path for path in ROOT.rglob("*") if ".git" not in path.parts]
    return [
        path
        for path in paths
        if path.is_file()
        and (path.suffix in REFERENCE_SUFFIXES or path.name == "Makefile")
        and not str(path.relative_to(ROOT)).startswith(REFERENCE_EXEMPT)
    ]


def check_references(
    report: Report,
    open_needs: list[Document],
    provided: list[Document],
    open_docs: list[Document],
    files: list[Path] | None = None,
) -> None:
    """Every needs request named resolves to a record that will be, or was, provided; every
    action left to the owner in a `TODO(owner)` is an open record (ADR-0028)."""
    print("references")
    needs = {doc.number: doc for doc in [*open_needs, *provided]}
    open_records = {f"NEED-{doc.number}" for doc in open_needs} | {
        f"DEC-{doc.number}" for doc in open_docs
    }
    checked = 0
    for path in files if files is not None else repository_files():
        rel = str(path.relative_to(ROOT))
        in_register = rel.startswith("docs/decisions/")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines, start=1):
            for ref in NEED_REF.findall(line):
                checked += 1
                need = needs.get(ref)
                if need is None:
                    report.fail(f"{rel}:{number}", f"NEED-{ref} has no file")
                elif superseded(need) and not in_register:
                    report.fail(
                        f"{rel}:{number}",
                        f"NEED-{ref} was superseded and will not be provided; name the need that "
                        "took its place",
                    )
            # A marker quoted in a code span is the rule being described, not an action.
            if TODO_OWNER.search(re.sub(r"`[^`\n]*`", "", line)):
                checked += 1
                named = {f"{p}-{n}" for p, n in re.findall(r"\b(NEED|DEC)-(\d{4})\b", line)}
                if not named & open_records:
                    report.fail(
                        f"{rel}:{number}",
                        "`TODO(owner)` names no open needs request or decision request; an "
                        "action left to the owner is a record with an issue (ADR-0028)",
                    )
    report.ok(f"{checked} reference(s) to a need or an owner action across the repository")


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
        index = index_section("Decisions")
        unlisted = [doc for doc in records if doc.path.name not in index]
        if unlisted:
            report.fail(
                str(INDEX.relative_to(ROOT)),
                "not listed under Decisions: " + ", ".join(doc.path.name for doc in unlisted),
            )
        else:
            report.ok(f"{INDEX.relative_to(ROOT)} lists every record under Decisions")
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


def description_sections(body: str) -> list[tuple[str, str]]:
    """`(heading, text)` for every `## ` heading of a description, comments removed."""
    found: list[tuple[str, str]] = []
    current: str | None = None
    buffer: list[str] = []
    for line in strip_comments(body).splitlines():
        if line.startswith("## "):
            if current is not None:
                found.append((current, "\n".join(buffer).strip()))
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        found.append((current, "\n".join(buffer).strip()))
    return found


def check_description(body: str, report: Report) -> None:
    print("description")
    found = description_sections(body)
    by_name = {name.lower(): text for name, text in found}
    order = [name.lower() for name, _ in found]
    problems: list[str] = []
    positions: list[int] = []
    for name in DESCRIPTION:
        key = name.lower()
        if key not in by_name:
            problems.append(f"no `## {name}`")
            continue
        positions.append(order.index(key))
        text = by_name[key]
        if not text:
            problems.append(f"`## {name}` is empty")
        elif hit := PLACEHOLDER.search(strip_code(text)):
            problems.append(f"`## {name}` keeps a placeholder: {hit.group(0)!r}")
    if not problems and positions != sorted(positions):
        problems.append("the four sections are out of order: " + ", ".join(DESCRIPTION))
    if problems:
        report.fail(
            "description",
            "; ".join(problems)
            + " — every description says, without assuming the diff, what the change is about, "
            "what was done, why that way, and what to check (ADR-0017 §7)",
        )
    else:
        report.ok("the description says what, what was done, why, and what to check")


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


# --- who wrote the description -----------------------------------------------------------------

DEPENDENCY_BOTS = frozenset({"dependabot[bot]"})
"""Authors whose descriptions the shape is not asked of: a dependency bot writes its own
description — what is bumped, from which version to which, the upstream release notes — and
never the repository's sections. That serves the check's purpose, that the owner understands
what he reviews; asking it of a bot would fail every such pull request for ever. Every code gate,
the register and the status gates still run on its pull requests (NTC-0013). A pull request
written by a session or by Taktus — under the owner's login, today — is held to the shape."""


def written_by_a_dependency_bot(author: str | None) -> bool:
    return author is not None and author in DEPENDENCY_BOTS


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
        "--author", help="github.event.pull_request.user.login: who wrote the description"
    )
    parser.add_argument(
        "--forbid-open-blocking",
        action="store_true",
        help="fail on any BLOCKING file under open/ (use on the main branch)",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    report = Report()
    open_docs, records = check_register(report)
    notices = check_notices(report)
    check_override_review(report, notices, [*open_docs, *records])
    open_needs, provided_needs = check_needs(report)
    check_credentials(report, [*open_needs, *provided_needs])
    check_references(report, open_needs, provided_needs, open_docs)
    if args.pr_body is not None and written_by_a_dependency_bot(args.author):
        print("description")
        report.ok(
            f"written by {args.author}, a dependency bot, which carries its own explanation; "
            "the shape is asked of a session's and Taktus's descriptions (NTC-0013)"
        )
    elif args.pr_body is not None:
        body = args.pr_body.read_text(encoding="utf-8")
        check_description(body, report)
        check_pull_request(body, args.draft, open_docs, report)
    if args.forbid_open_blocking:
        for doc in open_docs:
            if doc.category == "BLOCKING":
                report.fail(
                    doc.rel, "BLOCKING request on the main branch; it was merged unanswered"
                )
    print()
    duration = f"{time.monotonic() - started:.2f}s"
    if report.failures:
        print(f"{report.passed} passed, {len(report.failures)} failed in {duration}")
        return 1
    print(f"{report.passed} passed in {duration}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
