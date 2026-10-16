# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Every ADR that makes a promise states where the promise ends.

Runs as `make gate-adrs`. Standard library only, so `uv run tools/check_adrs.py` and
`python3 tools/check_adrs.py` both work without the project installed.

A promise without a stated boundary reads as a guarantee. ADR-0005 said "no limit is ever
breached" and a currency limit could be; ADR-0014 said `exact` is machine-checkable and did not
say that somebody has to write the check. Both boundaries were documented somewhere other than
where the promise was made. Hence the rule (docs/adr/README.md): an ADR that promises carries the
section `## Where this promise ends`, and this gate fails one that does not.

Checks, per `docs/adr/ADR-NNNN-*.md`:

1. the first line is `# ADR-NNNN — Title` and a `**Status:**` line follows;
2. the ADR is listed in `docs/adr/README.md`;
3. an ADR that *promises* — its prose, outside code and outside the section itself, carries a
   promise marker such as "never", "always", "guarantee", "immutable", "at most", "exactly",
   "cannot", "must" — has the section `## Where this promise ends`, as the last section;
4. the section is not empty, keeps no placeholder, is not a bare pointer to another document,
   and is at least three sentences long: a boundary is stated, not referenced.

An ADR without a promise marker may omit the section; the gate says so per file. A directory
with no ADR reports green and says so.

5. every `ADR-NNNN` named in a tracked Markdown, Python or YAML file under `docs/`, `src/`,
   `tools/`, `blueprints/`, `deploy/`, `contracts/`, `tests/`, or in `CLAUDE.md`,
   `CREDENTIALS.md`, `README.md`, resolves to a file `docs/adr/ADR-NNNN-*.md`. NEED-0024 cited
   an ADR nobody wrote and every gate passed it (DEC-0178). Whether the reference names the right
   ADR is not checked, only that the ADR exists.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SECTION = "Where this promise ends"
TITLE = re.compile(r"^# ADR-(\d{4}) — (.+)$")
FILENAME = re.compile(r"^ADR-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
STATUS = re.compile(r"^\*\*Status:\*\*\s*\S")
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME|XXX)\b|…")
# The words a promise is made with. Matched as whole words, case-insensitively, in prose.
PROMISE = re.compile(
    r"\b(never|always|ever|guarantee[sd]?|immutable|at most|at least|exactly|cannot|must|"
    r"no [a-z]+ is ever|every [a-z]+ (?:carries|is|has))\b",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
MIN_SENTENCES = 3
POINTER_ONLY = re.compile(r"^\s*(?:see|refer to)\b", re.IGNORECASE)
# Where a reference to an ADR is resolved: these directories and files, these suffixes.
REFERENCE_DIRS = ("docs", "src", "tools", "blueprints", "deploy", "contracts", "tests")
REFERENCE_FILES = ("CLAUDE.md", "CREDENTIALS.md", "README.md")
REFERENCE_SUFFIXES = frozenset({".md", ".py", ".yaml", ".yml"})
REFERENCE = re.compile(r"\bADR-(\d{4})\b")


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


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def sections(text: str) -> list[tuple[str, str]]:
    """`(heading, body)` for every `## ` heading, in order."""
    found: list[tuple[str, str]] = []
    current: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
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


def check(root: Path, path: Path, index: str, report: Report) -> None:
    rel = str(path.relative_to(root))
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = TITLE.match(lines[0]) if lines else None
    if title is None:
        report.fail(rel, "first line is not `# ADR-NNNN — Title`")
        return
    name = FILENAME.match(path.name)
    if name is None:
        problems.append("file name is not ADR-NNNN-<slug>.md with a lowercase slug")
    elif name.group(1) != title.group(1):
        problems.append(f"file name says ADR-{name.group(1)}, title says ADR-{title.group(1)}")
    if not any(STATUS.match(line) for line in lines[1:6]):
        problems.append("no `**Status:**` line after the title")
    if path.name not in index:
        problems.append("not listed in docs/adr/README.md")

    parts = sections(text)
    ends = [body for heading, body in parts if heading == SECTION]
    prose = strip_code("\n".join(body for heading, body in parts if heading != SECTION))
    promise = PROMISE.search(prose)
    if ends:
        body = ends[0]
        if parts[-1][0] != SECTION:
            problems.append(f"`## {SECTION}` is not the last section")
        if len(ends) > 1:
            problems.append(f"`## {SECTION}` appears {len(ends)} times")
        if not body:
            problems.append(f"`## {SECTION}` is empty")
        else:
            if found := PLACEHOLDER.search(strip_code(body)):
                problems.append(f"`## {SECTION}` keeps a placeholder: {found.group(0)!r}")
            if len(SENTENCE_END.findall(body)) < MIN_SENTENCES:
                problems.append(
                    f"`## {SECTION}` has fewer than {MIN_SENTENCES} sentences: state the "
                    "boundary, do not point at it"
                )
            if POINTER_ONLY.match(body):
                problems.append(f"`## {SECTION}` is a pointer to another document, not a boundary")
    elif promise is not None:
        problems.append(
            f"promises (`{promise.group(0)}`) without `## {SECTION}`: state where the promise "
            "ends, in the ADR that makes it"
        )
    if problems:
        report.fail(rel, "; ".join(problems))
    else:
        report.ok(rel + ("" if ends else " (no promise made; section optional)"))


def tracked(root: Path) -> list[Path]:
    """The files a reference is resolved in: tracked by Git, or every file outside a repository."""

    def git(*args: str) -> str:
        # A fixed executable name and arguments assembled here, not from input: nothing untrusted.
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip

    try:
        top, listed = git("rev-parse", "--show-toplevel").strip(), git("ls-files", "-z")
    except (OSError, subprocess.CalledProcessError):
        top, listed = "", ""
    if top and Path(top).resolve() == root.resolve():
        names = [name for name in listed.split("\0") if name]
    else:
        names = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    paths = []
    for name in sorted(names):
        parts = Path(name).parts
        if Path(name).suffix not in REFERENCE_SUFFIXES:
            continue
        if name in REFERENCE_FILES or (len(parts) > 1 and parts[0] in REFERENCE_DIRS):
            paths.append(root / name)
    return paths


def check_references(root: Path, report: Report) -> None:
    """Every `ADR-NNNN` named in a reference file has its file under `docs/adr/`."""
    adrs = root / "docs" / "adr"
    numbers = {
        m.group(1)
        for p in (adrs.glob("ADR-*.md") if adrs.is_dir() else [])
        if (m := re.match(r"ADR-(\d{4})-", p.name))
    }
    dangling = 0
    for path in tracked(root):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for found in REFERENCE.finditer(line):
                if found.group(1) not in numbers:
                    dangling += 1
                    report.fail(
                        f"{rel}:{number}",
                        f"names ADR-{found.group(1)}, and no docs/adr/ADR-{found.group(1)}-*.md "
                        "exists",
                    )
    if not dangling:
        report.ok("every ADR named in the repository has its file")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="the repository's root")
    root: Path = parser.parse_args(argv).root
    adrs = root / "docs" / "adr"
    index_path = adrs / "README.md"
    report = Report()
    print("architecture decision records")
    index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    paths = sorted(adrs.glob("ADR-*.md")) if adrs.is_dir() else []
    if not paths:
        report.ok("no ADR yet — nothing to check, reporting green")
    for path in paths:
        check(root, path, index, report)
    print()
    print("references to architecture decision records")
    check_references(root, report)
    print()
    if report.failures:
        print(f"{report.passed} passed, {len(report.failures)} failed")
        return 1
    print(f"{report.passed} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
