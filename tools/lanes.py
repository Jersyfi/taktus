# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Which lanes of CI a change selects: the same code for CI and for `make verify` (ADR-0096 §3).

A lane is a job of `.github/workflows/ci.yml`. `static` and `decisions` always run: they are
the always-on checks and the documentation and register gates, and take a few minutes. The
others run when a path they claim changed. A path that changes what every lane runs on — the
project's dependencies, the build, CI itself, the contracts, the shared kernel — selects every
lane. Every tracked path is claimed by at least one lane; `tests/architecture` fails one that
is not, so that no change can slip past every lane.

    tools/lanes.py --base REF                  the lanes the change against REF selects
    tools/lanes.py --all                       every lane (a push to `main` runs everything)
    tools/lanes.py ... --github-output FILE    also write `<lane>=true|false` lines for CI
    tools/lanes.py --unclaimed                 the tracked paths no lane claims; exit 1 if any
    tools/lanes.py ... --commands              the make targets of the selected lanes, one a line

    tools/lanes.py --tests --base REF          the test files the change selects in `test`

Inside the Python core the tests are selected by the import graph (#394, ADR-0096 §3): the
modules a change touches, every module that imports them directly or through others, and the
test files among those. `make check`, `make verify` and CI's lane `test` read this one
implementation. The graph is the one `import-linter` enforces — static imports of `taktus` —
read here from the source with the standard library, so that the script needs no environment.
Code reached by a string is selected by path, not by the graph: a string that names a module
(an entry point, `-m taktus.x` for a subprocess) is an edge as well, and a change to anything
that is not a Python module of the core or of the tests — a template, a recording, a tool, a
bundle, a migration — selects every test, as does a file the graph cannot place (a deleted or
renamed one). The lane `rehearse` is not selected by component: a change under `src/` selects it
whole.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ALWAYS = ("static", "decisions")
SELECTABLE = ("contracts", "web", "conformance", "test", "rehearse")
LANES = ALWAYS + SELECTABLE

# A path matching one of these selects every lane.
EVERYTHING = (
    r"pyproject\.toml",
    r"uv\.lock",
    r"\.python-version",
    r"Makefile",
    r"\.github/.*",
    r"contracts/.*",
    r"src/taktus/shared/.*",
    r"tests/conftest\.py",
)

CLAIMS: dict[str, tuple[str, ...]] = {
    # Read by the always-on checks: lint, types, architecture, chart, governance, exactness,
    # documentation freshness, decisions, use cases, ADRs, vision, status.
    "static": (r".*",),
    "decisions": (r".*",),
    "contracts": (r"api/.*", r"tools/(validate_contracts|generate)\.py"),
    "web": (r"web/.*",),
    "conformance": (
        r"src/taktus/(conformance|wire|ports|adapters)/.*",
        r"workers/.*",
        r"tests/conformance/.*",
        r"tests/fakes/.*",
    ),
    "test": (
        r"src/.*",
        r"tests/(?!conformance/).*",
        r"migrations/.*",
        r"blueprints/.*",
        r"examples/.*",
        r"deploy/.*",
        r"workers/.*",
        r"tools/.*",
        r"\.claude/(settings\.json|hooks/.*)",
        r"\.importlinter",
        r"\.dockerignore",
        r"\.env\.example",
    ),
    # The replay of the self-development bundles (ADR-0108): the bundles, the recordings and
    # what replays them. It reaches the core through the composition root, whose import graph
    # holds nearly every module under `src/`, so every change there selects it;
    # `tests/tools/test_lanes.py` holds the claim to the modules the replay imports.
    "rehearse": (
        r"src/.*",
        r"blueprints/.*",
        r"migrations/.*",
        r"tests/rehearsal/.*",
        r"tests/integration/test_rehearsal_recordings\.py",
        r"tools/record_rehearsal\.py",
    ),
}

# What each lane runs, as CI's job runs it.
COMMANDS: dict[str, tuple[str, ...]] = {
    "static": (
        "lint",
        "gate-arch",
        "gate-governance",
        "gate-exactness",
        "gate-docs",
        "gate-decisions",
        "gate-usecases",
    ),
    "decisions": ("gate-adrs", "gate-vision", "gate-status"),
    "contracts": ("gate-contracts",),
    "web": ("gate-web",),
    "conformance": ("gate-conformance",),
    "test": ("test",),
    "rehearse": ("rehearse",),
}


def _matches(patterns: tuple[str, ...], path: str) -> bool:
    return any(re.fullmatch(pattern, path) for pattern in patterns)


def select(paths: list[str]) -> list[str]:
    """The lanes the changed paths select, in the order of LANES."""
    if any(_matches(EVERYTHING, path) for path in paths):
        return list(LANES)
    chosen = set(ALWAYS)
    for lane in SELECTABLE:
        if any(_matches(CLAIMS[lane], path) for path in paths):
            chosen.add(lane)
    return [lane for lane in LANES if lane in chosen]


def unclaimed(paths: list[str]) -> list[str]:
    """The paths no selectable lane claims and that do not select everything: what only the
    always-on checks read. Documentation is meant to be here; anything else is a hole."""
    return [
        path
        for path in paths
        if not _matches(EVERYTHING, path)
        and not any(_matches(CLAIMS[lane], path) for lane in SELECTABLE)
    ]


DOCUMENTATION = (
    r"docs/.*",
    r"[A-Z][A-Z_]*\.md",
    r"LICENSE",
    r"NOTICE",
    r"\.gitignore",
)


def holes(paths: list[str]) -> list[str]:
    """Tracked paths that only the always-on checks read and that are not documentation."""
    return [path for path in unclaimed(paths) if not _matches(DOCUMENTATION, path)]


# --- Selection of tests inside the lane `test` (#394) ---------------------------------------

ALL_TESTS = "tests"
_MODULE_IN_STRING = re.compile(r"\btaktus(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def _dotted(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _python_files() -> list[Path]:
    files = [*(ROOT / "src" / "taktus").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]
    return sorted(f.relative_to(ROOT) for f in files if "__pycache__" not in f.parts)


def import_graph() -> dict[str, set[str]]:
    """Path -> the paths of the Python files it imports, from `src/taktus` and `tests`.

    Importing `a.b.c` also runs `a/__init__.py` and `a/b/__init__.py`, so those are edges. A
    test file depends on every `conftest.py` above it."""
    files = _python_files()
    modules = {_dotted(f): str(f) for f in files}
    graph: dict[str, set[str]] = {str(f): set() for f in files}

    def link(source: str, module: str) -> None:
        parts = module.split(".")
        for end in range(1, len(parts) + 1):
            target = modules.get(".".join(parts[:end]))
            if target and target != source:
                graph[source].add(target)

    for file in files:
        source = str(file)
        package = _dotted(file) if file.name == "__init__.py" else _dotted(file).rpartition(".")[0]
        tree = ast.parse((ROOT / file).read_text(encoding="utf-8"), filename=source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    link(source, alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    anchor = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                    base = ".".join([*anchor, *([base] if base else [])])
                link(source, base)
                for alias in node.names:
                    link(source, f"{base}.{alias.name}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for named in _MODULE_IN_STRING.findall(node.value):
                    while named and named not in modules:
                        named = named.rpartition(".")[0]
                    if named:
                        link(source, named)
        if file.parts[0] == "tests":
            for parent in file.parents:
                conftest = parent / "conftest.py"
                if parent.parts and str(conftest) in graph and str(conftest) != source:
                    graph[source].add(str(conftest))
    return graph


def select_tests(paths: list[str], graph: dict[str, set[str]] | None = None) -> list[str]:
    """The test files the changed paths select, or `[ALL_TESTS]` for every test.

    A path the graph does not hold selects everything; so does one of the paths that select
    every lane. Otherwise: the changed files and every file that reaches them through imports,
    restricted to the test files."""
    if any(_matches(EVERYTHING, path) for path in paths):
        return [ALL_TESTS]
    graph = import_graph() if graph is None else graph
    changed_nodes = set()
    for path in paths:
        if path in graph:
            changed_nodes.add(path)
        elif _matches(DOCUMENTATION, path):
            continue
        else:
            return [ALL_TESTS]
    dependents: dict[str, set[str]] = {node: set() for node in graph}
    for node, targets in graph.items():
        for target in targets:
            dependents[target].add(node)
    reached, queue = set(changed_nodes), list(changed_nodes)
    while queue:
        for dependent in dependents[queue.pop()]:
            if dependent not in reached:
                reached.add(dependent)
                queue.append(dependent)
    return sorted(
        node
        for node in reached
        if node.startswith("tests/") and Path(node).name.startswith("test_")
    )


def _git(*args: str) -> str:
    # A fixed executable name and arguments assembled here, not from input: nothing untrusted.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip


def changed(base: str) -> list[str]:
    merge_base = _git("merge-base", base, "HEAD").strip()
    tracked = _git("diff", "--name-only", merge_base).splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked) | set(untracked))


def _restrict(found: list[str], within: list[str], exclude: list[str]) -> list[str]:
    """Narrow a selection to the directories a target runs. `tests` (all) becomes the
    directories themselves; a file outside them drops out."""
    roots = [Path(w) for w in within] or [Path(ALL_TESTS)]
    if found == [ALL_TESTS]:
        return [str(root) for root in roots]
    kept = [f for f in found if any(Path(r) in (Path(f), *Path(f).parents) for r in roots)]
    return [f for f in kept if not any(Path(x) in Path(f).parents for x in exclude)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--base", help="the ref the change is measured against")
    which.add_argument("--all", action="store_true", help="every lane")
    which.add_argument("--unclaimed", action="store_true", help="tracked paths no lane claims")
    parser.add_argument("--github-output", type=Path, help="append `<lane>=true|false` here")
    parser.add_argument("--tests", action="store_true", help="with --base: the test files")
    parser.add_argument("--exclude", action="append", default=[], help="with --tests: a directory")
    parser.add_argument("--within", action="append", default=[], help="with --tests: a directory")
    parser.add_argument("--commands", action="store_true", help="print the make targets")
    args = parser.parse_args(argv)

    if args.tests and not args.base:
        parser.error("--tests needs --base")
    if args.tests:
        # A base that cannot be read — a clone that never fetched it — selects everything.
        try:
            found = select_tests(changed(args.base))
        except subprocess.CalledProcessError:
            found = [ALL_TESTS]
        print("\n".join(_restrict(found, args.within, args.exclude)))
        return 0
    if args.unclaimed:
        found = holes(_git("ls-files").splitlines())
        print("\n".join(found))
        return 1 if found else 0
    lanes = list(LANES) if args.all else select(changed(args.base))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            for lane in LANES:
                output.write(f"{lane}={'true' if lane in lanes else 'false'}\n")
    if args.commands:
        print("\n".join(target for lane in lanes for target in COMMANDS[lane]))
    else:
        print(" ".join(lanes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
