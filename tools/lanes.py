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

Not the selection by component inside the Python core (#394): a change under `src/` selects
the whole `test` lane, and the lane `rehearse` with it.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--base", help="the ref the change is measured against")
    which.add_argument("--all", action="store_true", help="every lane")
    which.add_argument("--unclaimed", action="store_true", help="tracked paths no lane claims")
    parser.add_argument("--github-output", type=Path, help="append `<lane>=true|false` here")
    parser.add_argument("--commands", action="store_true", help="print the make targets")
    args = parser.parse_args(argv)

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
