# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Documentation freshness: a contract or behaviour change touches its documentation.

Runs as `make gate-docs`. Standard library only. Compares the current branch with a base
(`--base`, default `origin/main`, then `main`) and applies the rules below to the files that
changed. A rule is satisfied when at least one of the documents it names changed too. A change
that matches no rule needs no documentation by this gate. No changed file at all, or none that
matches a rule, reports green and says so.

The rules are the documented places of the repository (docs/architecture/project-structure.md).
Adding a code area means adding its rule here.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Rule:
    """`trigger` is a regular expression on the changed path; `documents` are glob patterns, which
    may use the trigger's named groups (`{family}`)."""

    what: str
    trigger: str
    documents: tuple[str, ...]

    def documents_for(self, path: str) -> list[str] | None:
        match = re.fullmatch(self.trigger, path)
        if match is None:
            return None
        return [pattern.format(**match.groupdict()) for pattern in self.documents]


RULES: tuple[Rule, ...] = (
    Rule(
        "a contract",
        r"contracts/(?P<family>[a-z]+)/(?P<version>v\d+)/(?!examples/)[^/]+",
        ("contracts/{family}/{version}/README.md",),
    ),
    Rule(
        "a tool or a make target",
        r"(tools/[^/]+\.(?:py|sh)|Makefile)",
        ("tools/README.md",),
    ),
    Rule(
        "the architecture contracts",
        r"\.importlinter|tests/architecture/.*",
        ("docs/architecture/project-structure.md", "docs/adr/*.md"),
    ),
    Rule(
        "a component",
        r"src/taktus/components/.*",
        ("docs/architecture/*.md", "docs/adr/*.md"),
    ),
    Rule(
        "a port or an adapter",
        r"src/taktus/(ports|adapters)/.*",
        ("docs/architecture/contracts.md", "docs/architecture/project-structure.md"),
    ),
    Rule(
        "the composition root",
        r"src/taktus/composition/.*",
        ("docs/architecture/project-structure.md",),
    ),
    Rule(
        "a wire format",
        r"src/taktus/wire/.*",
        ("docs/architecture/project-structure.md",),
    ),
    Rule(
        "an example",
        r"examples/.*",
        ("examples/README.md",),
    ),
    Rule(
        "a worker",
        r"workers/(?P<name>[a-z]+)/.*",
        ("workers/{name}/README.md", "docs/architecture/contracts.md"),
    ),
    Rule(
        "a blueprint",
        r"blueprints/(?P<name>[a-z-]+)/.*",
        ("blueprints/{name}/README.md", "docs/usecases/*.md"),
    ),
    Rule(
        "a deployment",
        r"deploy/(?P<kind>[a-z0-9-]+)/.*",
        ("deploy/{kind}/README.md",),
    ),
)


def git(*args: str) -> str:
    # A fixed executable name and arguments assembled here, not from input: nothing untrusted.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def resolve_base(requested: str | None) -> str | None:
    candidates = [requested] if requested else ["origin/main", "main"]
    for candidate in candidates:
        try:
            git("rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}")
        except RuntimeError:
            continue
        return candidate
    return None


def changed_files(base: str) -> list[str]:
    committed = git("diff", "--name-only", f"{base}...HEAD").split()
    working = git("status", "--porcelain", "--untracked-files=all")
    uncommitted = [line[3:].split(" -> ")[-1] for line in working.splitlines() if line.strip()]
    return sorted(set(committed) | set(uncommitted))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", help="commit or branch to compare with (default origin/main)")
    args = parser.parse_args(argv)

    base = resolve_base(args.base)
    if base is None:
        print(f"base {args.base or 'origin/main or main'} not found; cannot tell what changed")
        return 1
    changed = changed_files(base)
    if not changed:
        print(f"no changes against {base}; nothing to check, reporting green")
        return 0

    failures: list[str] = []
    checked = 0
    for path in changed:
        if path.endswith(".md"):
            continue  # documentation documents itself
        for rule in RULES:
            documents = rule.documents_for(path)
            if documents is None:
                continue
            checked += 1
            touched = [d for d in changed if any(fnmatch.fnmatchcase(d, p) for p in documents)]
            if touched:
                print(f"  ok   {path} ({rule.what}) — {touched[0]}")
            else:
                wanted = ", ".join(documents)
                failures.append(f"{path} changes {rule.what} but none of: {wanted}")
                print(f"  FAIL {path}\n       changes {rule.what}; touch one of: {wanted}")
            break
    print()
    if failures:
        print(f"{checked - len(failures)} passed, {len(failures)} failed")
        return 1
    if checked == 0:
        print(f"{len(changed)} changed file(s) against {base}, none needs documentation by rule")
    else:
        print(f"{checked} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
