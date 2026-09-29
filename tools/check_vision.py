# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""The vision layer holds together, and every principle is served by a use case.

Runs as `make gate-vision`. Standard library only, so `uv run tools/check_vision.py` and
`python3 tools/check_vision.py` both work without the project installed.

`docs/vision/` says why Taktus exists and what it refuses to be; it is what point 1 of the
definition of done, *violates no guiding principle*, is checked against. It is mode 4: the
owner's (docs/decisions/anchors.taktus.md, M4.5).

Checks:

1. every file of `docs/vision/` is listed in its README;
2. `docs/vision/principles.md` has the fourteen principles as `## N — Title`, in order, with the
   titles `CLAUDE.md` §5 gives them — the doctrine and the vision say the same thing;
3. every principle states why it exists (`**Why.**`) and what it forbids (`**Forbids.**`): a
   principle that forbids nothing decides nothing;
4. `docs/vision/market.md` opens with its staleness warning and the month it was established;
5. every principle is served by at least one use case that is not retired — a principle nothing
   serves is either a missing requirement or an empty principle. The use cases are read with
   `tools/check_usecases.py`, which checks them in their own right.

The coverage is printed: which use cases serve which principle, with their states. The last
line is the duration.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# A sibling script, found through the line above.
from check_usecases import (
    PRINCIPLE_HEADING,
    PRINCIPLES,
    Report,
    UseCase,
    load_all,
    principles,
)

ROOT = Path(__file__).resolve().parent.parent
VISION = Path("docs/vision")
DOCTRINE = Path("CLAUDE.md")
MARKET = VISION / "market.md"
COUNT = 14
STALE = re.compile(
    r"^> \*\*Stale by construction\. Last established: "
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r" \d{4}\."
)
DOCTRINE_ITEM = re.compile(r"(?:^|\s)(\d{1,2})\. (.+?)(?=\s\d{1,2}\. |\Z)", re.DOTALL)


def normalise(title: str) -> str:
    title = re.sub(r"\*\*.*?\*\*", "", title)
    title = title.split(" — ")[0]
    return " ".join(title.split()).rstrip(".").strip().lower()


def doctrine_titles(root: Path) -> dict[int, str]:
    """The fourteen principles as CLAUDE.md §5 lists them."""
    text = (root / DOCTRINE).read_text(encoding="utf-8")
    section = text.split("## 5.", 1)[-1].split("\n## ", 1)[0]
    paragraphs = [p for p in section.split("\n\n")[1:] if re.match(r"\s*1\. ", p)]
    if not paragraphs:
        return {}
    joined = " ".join(paragraphs[0].split())
    return {int(n): normalise(t) for n, t in DOCTRINE_ITEM.findall(joined)}


def check_listing(root: Path, report: Report) -> None:
    print("the layer")
    folder = root / VISION
    if not folder.is_dir():
        report.fail(VISION.as_posix(), "missing")
        return
    readme = folder / "README.md"
    if not readme.is_file():
        report.fail(VISION.as_posix(), "has no README.md")
        return
    text = readme.read_text(encoding="utf-8")
    files = sorted(p.name for p in folder.glob("*.md") if p.name != "README.md")
    unlisted = [name for name in files if f"]({name})" not in text]
    if unlisted:
        report.fail((VISION / "README.md").as_posix(), "does not list " + ", ".join(unlisted))
    else:
        report.ok(f"{len(files)} file(s), every one listed in the README")


def principle_bodies(text: str) -> dict[int, tuple[str, str]]:
    found: dict[int, tuple[str, str]] = {}
    matches = list(PRINCIPLE_HEADING.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        found[int(match.group(1))] = (match.group(2).strip(), text[match.end() : end])
    return found


def check_principles(root: Path, report: Report) -> None:
    print("principles")
    path = root / PRINCIPLES
    if not path.is_file():
        report.fail(PRINCIPLES.as_posix(), "missing")
        return
    text = path.read_text(encoding="utf-8")
    numbers = [int(n) for n, _ in PRINCIPLE_HEADING.findall(text)]
    if numbers != list(range(1, COUNT + 1)):
        report.fail(
            PRINCIPLES.as_posix(), f"principles numbered {numbers}, not 1 to {COUNT} in order"
        )
        return
    doctrine = doctrine_titles(root)
    if sorted(doctrine) != list(range(1, COUNT + 1)):
        report.fail(DOCTRINE.as_posix(), f"§5 does not list {COUNT} principles as `N. Title.`")
        return
    for number, (title, body) in principle_bodies(text).items():
        problems: list[str] = []
        if normalise(title) != doctrine[number]:
            problems.append(f"titled {title!r}; {DOCTRINE} §5 says {doctrine[number]!r}")
        for marker in ("**Why.**", "**Forbids.**"):
            if marker not in body:
                problems.append(f"no {marker}")
        if problems:
            report.fail(f"principle {number}", "; ".join(problems))
        else:
            report.ok(f"P{number} {title}: why, and what it forbids")


def check_market(root: Path, report: Report) -> None:
    print("market")
    path = root / MARKET
    if not path.is_file():
        report.fail(MARKET.as_posix(), "missing")
        return
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    warning = next((line for line in lines if line.startswith(">")), "")
    if STALE.match(warning):
        report.ok("the market picture says it is stale, and since when")
    else:
        report.fail(
            MARKET.as_posix(),
            "does not open with `> **Stale by construction. Last established: <Month YYYY>.`",
        )


def check_coverage(root: Path, report: Report) -> None:
    print("every principle served")
    names = principles(root)
    cases: list[UseCase] = [c for c in load_all(root) if c.state != "retired"]
    for key, title in names.items():
        serving = [c for c in cases if key in c.serves]
        if serving:
            listed = ", ".join(f"{c.id} ({c.state})" for c in serving)
            report.ok(f"{key} {title}: {listed}")
        else:
            report.fail(
                f"{key} {title}",
                "no use case serves it — either a requirement is missing or the principle is empty",
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    started = time.monotonic()
    report = Report()
    check_listing(root, report)
    check_principles(root, report)
    check_market(root, report)
    check_coverage(root, report)
    print()
    duration = f"{time.monotonic() - started:.2f}s"
    if report.failures:
        print(f"{report.passed} passed, {len(report.failures)} failed in {duration}")
        return 1
    print(f"{report.passed} passed in {duration}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
