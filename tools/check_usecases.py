# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""The use cases are requirements the implementation is held to (docs/usecases/README.md).

Runs as `make gate-usecases`. Standard library only, so `uv run tools/check_usecases.py` and
`python3 tools/check_usecases.py` work without the project installed — except for a use case in
state `verified`, whose named tests are run with pytest from the project environment.

A use case is a file `docs/usecases/<component>/UC-<area>.<case>-<slug>.md`: front matter, then
the requirement in three sections — what must be achieved, how it is verified, where the boundary
lies — and a fourth that says what it rests on.

Checks, per use case:

1. it sits in the folder of a component that `docs/architecture/project-structure.md` §1 lists,
   its file name carries its id, and ids are unique;
2. its front matter has every field, and nothing else: `id`, `title`, `component`, `serves`,
   `state`, `version`, `tests`, `adrs`, `supersedes`, optionally `epic`;
3. it serves at least one principle, and every principle it names is one of
   `docs/vision/principles.md`;
4. its state is one of specified, building, built, verified, retired; its version is a milestone
   of `docs/roadmap.md`;
5. sections 1 to 3 are present, in order, not empty, no placeholder — a use case without a
   verification condition is not a requirement;
6. in state `built` or `verified` it names at least one test, and every test it names exists
   (`path::name`, a function of that name in that file);
7. in state `verified` its named tests pass: run with pytest, none failing, none skipped;
8. every ADR the file names is in `adrs`, with the digest of the ADR's text it was last checked
   against, and that digest is the ADR's digest now. An ADR that changed since is an ADR that may
   contradict the use case without having touched it; the gate names both, and the change that
   moved the ADR either records the new digest after checking or raises a decision request;
9. against a base (`--base`, default `origin/main`, then `main`): a pull request that changes what
   a use case requires — sections 1 to 3, or a use case that is new or removed — does not touch
   its implementation: its component's code under `src/taktus/components/<component>/`, its
   component's tests under `tests/components/<component>/`, or the files of the tests it names.

`--print` prints every use case with its component, state and version (`make usecases`).
`--digest ADR-NNNN` prints the digest to record. The last line is the duration.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

USECASES = Path("docs/usecases")
STRUCTURE = Path("docs/architecture/project-structure.md")
PRINCIPLES = Path("docs/vision/principles.md")
ROADMAP = Path("docs/roadmap.md")
ADRS = Path("docs/adr")

REQUIRED = ["id", "title", "component", "serves", "state", "version", "tests", "adrs", "supersedes"]
OPTIONAL = ["epic"]
STATES = ["specified", "building", "built", "verified", "retired"]
NEEDS_TESTS = {"built", "verified"}
SECTIONS = [
    "1. What must be achieved",
    "2. How it is verified",
    "3. Where the boundary lies",
]
DESCRIBED = "4. What it rests on"

FILENAME = re.compile(r"^(UC-\d+\.\d+)-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
USECASE_ID = re.compile(r"^UC-\d+\.\d+$")
PRINCIPLE_HEADING = re.compile(r"^## (\d+) — (.+)$", re.MULTILINE)
COMPONENT_ROW = re.compile(r"^\| `([a-z]+)` \|", re.MULTILINE)
MILESTONE = re.compile(r"^### `(\d+\.\d+\.\d+)`", re.MULTILINE)
ADR_REF = re.compile(r"\bADR-(\d{4})\b")
DIGEST = re.compile(r"^[0-9a-f]{12}$")
TEST_REF = re.compile(r"^(tests/[A-Za-z0-9_/]+\.py)::([A-Za-z_][A-Za-z0-9_]*)$")
PLACEHOLDER = re.compile(r"<[^>\n]+>|\b(?:TODO|TBD|FIXME|XXX)\b|…")
EPIC = re.compile(r"^E\d+$")


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
class UseCase:
    path: Path  # relative to the root
    fields: dict[str, object]
    sections: dict[str, str]
    order: list[str]
    body: str

    @property
    def id(self) -> str:
        return str(self.fields.get("id", self.path.stem))

    @property
    def component(self) -> str:
        return str(self.fields.get("component", ""))

    @property
    def state(self) -> str:
        return str(self.fields.get("state", ""))

    @property
    def serves(self) -> list[str]:
        value = self.fields.get("serves")
        return [str(v) for v in value] if isinstance(value, list) else []

    @property
    def tests(self) -> list[str]:
        value = self.fields.get("tests")
        return [str(v) for v in value] if isinstance(value, list) else []

    @property
    def adrs(self) -> dict[str, str]:
        value = self.fields.get("adrs")
        return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}

    def requirement(self) -> str:
        """Sections 1 to 3, whitespace-normalised: what the owner decides (M3.15)."""
        return "\n".join(" ".join(self.sections.get(name, "").split()) for name in SECTIONS)


# --- parsing -------------------------------------------------------------------------------------


class FrontMatterError(ValueError):
    pass


def parse_value(raw: str) -> object:
    raw = raw.strip()
    if raw == "null":
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [item.strip() for item in inner.split(",")] if inner else []
    if raw.startswith("{") and raw.endswith("}"):
        inner = raw[1:-1].strip()
        mapping: dict[str, str] = {}
        for item in inner.split(",") if inner else []:
            key, sep, value = item.partition(":")
            if not sep or not key.strip() or not value.strip():
                raise FrontMatterError(f"not a `key: value` pair: {item.strip()!r}")
            mapping[key.strip()] = value.strip()
        return mapping
    if raw.startswith(("[", "{")):
        raise FrontMatterError(f"unclosed list or mapping: {raw!r}")
    return raw


def parse(text: str) -> tuple[dict[str, object], str]:
    """The front matter as a dictionary, and the rest of the file."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontMatterError("the file does not start with `---` front matter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise FrontMatterError("the front matter is not closed with `---`") from None
    fields: dict[str, object] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not re.fullmatch(r"[a-z_]+", key):
            raise FrontMatterError(f"not a `key: value` line: {line!r}")
        if key in fields:
            raise FrontMatterError(f"`{key}` appears twice")
        fields[key] = parse_value(value)
    return fields, "\n".join(lines[end + 1 :])


def split_sections(body: str) -> tuple[dict[str, str], list[str]]:
    found: dict[str, str] = {}
    order: list[str] = []
    current: str | None = None
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current is not None:
                found[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            order.append(current)
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        found[current] = "\n".join(buffer).strip()
    return found, order


def strip_noise(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def load(root: Path, path: Path) -> UseCase:
    fields, body = parse((root / path).read_text(encoding="utf-8"))
    sections, order = split_sections(body)
    return UseCase(path, fields, sections, order, body)


def load_text(path: Path, text: str) -> UseCase | None:
    try:
        fields, body = parse(text)
    except FrontMatterError:
        return None
    sections, order = split_sections(body)
    return UseCase(path, fields, sections, order, body)


# --- the rest of the repository ------------------------------------------------------------------


def components(root: Path) -> set[str]:
    text = (root / STRUCTURE).read_text(encoding="utf-8")
    section = text.split("## 1. Components", 1)[-1].split("\n## ", 1)[0]
    return set(COMPONENT_ROW.findall(section))


def principles(root: Path) -> dict[str, str]:
    """`{"P1": title, …}` from the headings of docs/vision/principles.md."""
    path = root / PRINCIPLES
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    return {f"P{number}": title.strip() for number, title in PRINCIPLE_HEADING.findall(text)}


def milestones(root: Path) -> set[str]:
    return set(MILESTONE.findall((root / ROADMAP).read_text(encoding="utf-8")))


def adr_path(root: Path, number: str) -> Path | None:
    found = sorted((root / ADRS).glob(f"ADR-{number}-*.md"))
    return found[0] if found else None


def digest_of(path: Path) -> str:
    """The digest of an ADR's text, insensitive to trailing whitespace."""
    lines = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
    text = "\n".join(lines).strip() + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def discover(root: Path) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Every use case file, and every file under a component folder that is not one."""
    found: list[Path] = []
    stray: list[tuple[Path, str]] = []
    base = root / USECASES
    if not base.is_dir():
        return found, stray
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        for path in sorted(folder.rglob("*.md")):
            rel = path.relative_to(root)
            if path.name == "README.md" and path.parent == folder:
                continue
            if path.parent != folder:
                stray.append((rel, "nested below the component folder"))
            elif FILENAME.match(path.name) is None:
                stray.append((rel, "not named `UC-<area>.<case>-<slug>.md`"))
            else:
                found.append(rel)
    return found, stray


# --- checks --------------------------------------------------------------------------------------


def check_shape(
    root: Path,
    case: UseCase,
    known_components: set[str],
    known_principles: dict[str, str],
    known_milestones: set[str],
) -> list[str]:
    problems: list[str] = []
    fields = case.fields
    missing = [key for key in REQUIRED if key not in fields]
    unknown = [key for key in fields if key not in REQUIRED + OPTIONAL]
    if missing:
        problems.append("front matter lacks " + ", ".join(f"`{m}`" for m in missing))
    if unknown:
        problems.append("front matter has unknown " + ", ".join(f"`{u}`" for u in unknown))

    folder = case.path.parent.name
    match = FILENAME.match(case.path.name)
    if match and fields.get("id") != match.group(1):
        problems.append(f"`id` is {fields.get('id')!r}, the file name says {match.group(1)}")
    if folder not in known_components:
        problems.append(f"`{folder}/` is not a component of {STRUCTURE}")
    if fields.get("component") != folder:
        problems.append(f"`component` is {fields.get('component')!r}, the folder is `{folder}`")
    title = fields.get("title")
    if not isinstance(title, str) or not title or PLACEHOLDER.search(title):
        problems.append("`title` is empty or a placeholder")
    elif f"# {case.id} — {title}" not in case.body.splitlines():
        problems.append(f"the first heading is not `# {case.id} — {title}`")

    serves = fields.get("serves")
    if not isinstance(serves, list) or not serves:
        problems.append("serves no principle (`serves: [P…]`)")
    else:
        strange = [p for p in case.serves if p not in known_principles]
        if strange:
            problems.append(f"serves {', '.join(strange)}, not a principle of {PRINCIPLES}")

    state = fields.get("state")
    if state not in STATES:
        problems.append(f"`state` is {state!r}, not one of {', '.join(STATES)}")
    version = fields.get("version")
    if version not in known_milestones:
        problems.append(f"`version` {version!r} is not a milestone of {ROADMAP}")
    epic = fields.get("epic")
    if "epic" in fields and not (isinstance(epic, str) and EPIC.match(epic)):
        problems.append(f"`epic` is {epic!r}, not `E<n>`")
    supersedes = fields.get("supersedes")
    if supersedes is not None and not (
        isinstance(supersedes, str) and USECASE_ID.match(supersedes)
    ):
        problems.append(f"`supersedes` is {supersedes!r}, neither null nor a use case id")
    if not isinstance(fields.get("tests"), list):
        problems.append("`tests` is not a list")
    if not isinstance(fields.get("adrs"), dict):
        problems.append("`adrs` is not a mapping (`{ADR-NNNN: digest}`)")

    for name in SECTIONS:
        text = case.sections.get(name)
        if text is None:
            problems.append(f"no `## {name}`")
        elif not strip_noise(text).strip():
            problems.append(f"`## {name}` is empty")
        elif hit := PLACEHOLDER.search(strip_noise(text)):
            problems.append(f"`## {name}` keeps a placeholder: {hit.group(0)!r}")
    expected = [name for name in [*SECTIONS, DESCRIBED] if name in case.order]
    extra = [name for name in case.order if name not in [*SECTIONS, DESCRIBED]]
    if extra:
        problems.append("unexpected section(s): " + ", ".join(f"`## {e}`" for e in extra))
    elif case.order != expected:
        problems.append("sections are out of order")
    return problems


def check_tests(root: Path, case: UseCase) -> list[str]:
    problems: list[str] = []
    if case.state in NEEDS_TESTS and not case.tests:
        problems.append(f"state `{case.state}` names no test")
    for ref in case.tests:
        match = TEST_REF.match(ref)
        if match is None:
            problems.append(f"not a test reference `tests/…py::name`: {ref!r}")
            continue
        file, name = match.groups()
        path = root / file
        if not path.is_file():
            problems.append(f"{ref}: {file} does not exist")
        elif not re.search(
            rf"^(?:async )?def {re.escape(name)}\(", path.read_text(encoding="utf-8"), re.MULTILINE
        ):
            problems.append(f"{ref}: no test function `{name}` in {file}")
    return problems


def check_adrs(root: Path, case: UseCase) -> list[str]:
    problems: list[str] = []
    recorded = case.adrs
    for key, value in recorded.items():
        number = key.removeprefix("ADR-")
        if not re.fullmatch(r"\d{4}", number):
            problems.append(f"`adrs` key {key!r} is not `ADR-NNNN`")
            continue
        path = adr_path(root, number)
        if path is None:
            problems.append(f"{key} does not exist")
        elif not DIGEST.match(value):
            problems.append(f"{key}: {value!r} is not a digest; record {digest_of(path)}")
        elif value != digest_of(path):
            problems.append(
                f"{key} changed after this use case was checked against it "
                f"(recorded {value}, now {digest_of(path)}). Read both: if the use case still "
                f"holds, record the new digest; if the ADR contradicts it, raise a decision "
                f"request — what a use case requires is the owner's (M3.15)"
            )
    named = {f"ADR-{n}" for n in ADR_REF.findall(case.body)}
    unrecorded = sorted(named - set(recorded))
    if unrecorded:
        problems.append(
            "names " + ", ".join(unrecorded) + " but does not record it in `adrs` with a digest"
        )
    return problems


def run_tests(root: Path, refs: list[str]) -> tuple[bool, str]:
    """Run the named tests; green only if every one ran and passed."""
    try:
        import pytest  # noqa: F401
    except ImportError:
        return False, "pytest is not importable; run through `make gate-usecases`"
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.xml"
        # A fixed interpreter and arguments assembled here from checked test references.
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={report}",
                *refs,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if not report.exists():
            return False, "pytest produced no report"
        suite = ET.parse(report).getroot()  # noqa: S314 — pytest's own report, written just now
        if suite.tag == "testsuites":
            suite = suite[0]
        counts = {k: int(suite.get(k, "0")) for k in ("tests", "failures", "errors", "skipped")}
    if counts["tests"] == 0:
        return False, "no test was collected"
    if counts["failures"] or counts["errors"] or counts["skipped"]:
        return False, (
            f"{counts['tests']} run: {counts['failures']} failed, {counts['errors']} errors, "
            f"{counts['skipped']} skipped — a skipped test is not a green one"
        )
    return True, f"{counts['tests']} test(s) green"


# --- the diff ------------------------------------------------------------------------------------


def git(root: Path, *args: str) -> str:
    # A fixed executable name and arguments assembled here, not from input: nothing untrusted.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def resolve_base(root: Path, requested: str | None) -> str | None:
    for candidate in [requested] if requested else ["origin/main", "main"]:
        try:
            git(root, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}")
        except RuntimeError:
            continue
        return candidate
    return None


def changed_files(root: Path, base: str) -> set[str]:
    committed = git(root, "diff", "--name-only", f"{base}...HEAD").split()
    working = git(root, "status", "--porcelain", "--untracked-files=all")
    uncommitted = [line[3:].split(" -> ")[-1] for line in working.splitlines() if line.strip()]
    return set(committed) | set(uncommitted)


def at_base(root: Path, base: str, path: Path) -> UseCase | None:
    try:
        text = git(root, "show", f"{base}:{path.as_posix()}")
    except RuntimeError:
        return None
    return load_text(path, text)


def is_usecase_path(path: str) -> bool:
    parts = Path(path).parts
    return (
        len(parts) == len(USECASES.parts) + 2
        and Path(*parts[: len(USECASES.parts)]) == USECASES
        and FILENAME.match(parts[-1]) is not None
    )


def implementation(case: UseCase) -> list[str]:
    component = case.component
    paths = [f"src/taktus/components/{component}/", f"tests/components/{component}/"]
    paths += [ref.split("::", 1)[0] for ref in case.tests]
    return paths


def check_separation(root: Path, base: str | None, cases: list[UseCase], report: Report) -> None:
    print("requirement and implementation apart")
    resolved = resolve_base(root, base)
    if resolved is None:
        report.fail("base", f"{base or 'origin/main or main'} not found; cannot tell what changed")
        return
    changed = changed_files(root, resolved)
    by_path = {case.path.as_posix(): case for case in cases}
    touched: list[tuple[UseCase, str]] = []
    for path in sorted(p for p in changed if is_usecase_path(p)):
        head = by_path.get(path)
        before = at_base(root, resolved, Path(path))
        if head is None and before is None:
            continue
        if head is None and before is not None:
            touched.append((before, "removed"))
        elif head is not None and before is None:
            touched.append((head, "new"))
        elif head is not None and before is not None and head.requirement() != before.requirement():
            touched.append((head, "changed"))
    if not touched:
        report.ok(f"no requirement changed against {resolved}")
        return
    for case, how in touched:
        hits = sorted(
            path for path in changed for impl in implementation(case) if path.startswith(impl)
        )
        if hits:
            report.fail(
                case.path.as_posix(),
                f"requirement {how}, and its implementation too: "
                + ", ".join(hits[:5])
                + (" …" if len(hits) > 5 else "")
                + ". A use case is never changed in the pull request that implements it; raise "
                "a decision request with the point of failure and a worked proposal, and let the "
                "implementation wait (CLAUDE.md §9)",
            )
        else:
            report.ok(f"{case.id}: requirement {how}; its implementation untouched")


# --- main ----------------------------------------------------------------------------------------


def load_all(root: Path, report: Report | None = None) -> list[UseCase]:
    paths, stray = discover(root)
    if report is not None:
        for path, why in stray:
            report.fail(path.as_posix(), why)
    cases: list[UseCase] = []
    for path in paths:
        try:
            cases.append(load(root, path))
        except FrontMatterError as error:
            if report is not None:
                report.fail(path.as_posix(), str(error))
    return cases


def print_table(cases: list[UseCase]) -> None:
    print("| Use case | Title | Component | State | Version | Serves |")
    print("|---|---|---|---|---|---|")
    for case in sorted(cases, key=lambda c: [int(x) for x in c.id[3:].split(".")]):
        print(
            f"| {case.id} | {case.fields.get('title')} | `{case.component}` | {case.state} | "
            f"`{case.fields.get('version')}` | {', '.join(case.serves)} |"
        )
    counts = {state: sum(1 for c in cases if c.state == state) for state in STATES}
    print()
    print(", ".join(f"{n} {state}" for state, n in counts.items() if n) or "no use case yet")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--base", help="commit or branch to compare with (default origin/main)")
    parser.add_argument("--print", dest="show", action="store_true", help="print every use case")
    parser.add_argument("--digest", metavar="ADR-NNNN", help="print the digest of one ADR")
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    if args.digest:
        path = adr_path(root, args.digest.removeprefix("ADR-"))
        if path is None:
            print(f"{args.digest} does not exist", file=sys.stderr)
            return 1
        print(digest_of(path))
        return 0
    if args.show:
        print_table(load_all(root))
        return 0

    started = time.monotonic()
    report = Report()
    print("use cases")
    cases = load_all(root, report)
    known_components = components(root)
    known_principles = principles(root)
    known_milestones = milestones(root)
    seen: dict[str, Path] = {}
    for case in cases:
        rel = case.path.as_posix()
        if case.id in seen:
            report.fail(rel, f"{case.id} is also {seen[case.id].as_posix()}")
            continue
        seen[case.id] = case.path
        problems = check_shape(root, case, known_components, known_principles, known_milestones)
        problems += check_tests(root, case)
        problems += check_adrs(root, case)
        if problems:
            report.fail(rel, "; ".join(problems))
        else:
            report.ok(
                f"{case.id} ({case.component}, {case.state}, serves {', '.join(case.serves)})"
            )
    for case in cases:
        supersedes = case.fields.get("supersedes")
        if isinstance(supersedes, str) and supersedes not in seen:
            report.fail(case.path.as_posix(), f"supersedes {supersedes}, which has no file")
    retired = {c.id for c in cases if c.state == "retired"}
    replaced = {str(c.fields.get("supersedes")) for c in cases}
    for identifier in sorted(retired - replaced):
        report.fail(seen[identifier].as_posix(), "retired, and no use case supersedes it")
    if not cases:
        report.ok("no use case yet")

    verified = [c for c in cases if c.state == "verified" and c.tests]
    if verified:
        print("verified means green")
    for case in verified:
        green, what = run_tests(root, case.tests)
        if green:
            report.ok(f"{case.id}: {what}")
        else:
            report.fail(case.path.as_posix(), f"state `verified`, but {what}")

    check_separation(root, args.base, cases, report)

    print()
    duration = f"{time.monotonic() - started:.2f}s"
    if report.failures:
        print(f"{report.passed} passed, {len(report.failures)} failed in {duration}")
        return 1
    print(f"{report.passed} passed in {duration}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
