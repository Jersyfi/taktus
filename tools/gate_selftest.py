"""Every gate proves that it catches a violation (ADR-0096 §6 phase 3, #395).

Runs as `make gate-selftest`, from the project environment: `uv run python
tools/gate_selftest.py`, because the architecture gate and the named tests of a `verified` use
case need it. `--gate NAME` runs the cases of one gate, `--list` prints every case and runs
nothing.

A gate that stays green whatever it is given checks nothing, and nobody notices: green is what
everyone expects to see. So each documentation, register and architecture gate is fed a
deliberate violation here, one case at a time, and the self-test fails when the gate stays green.

How a case runs:

1. the working tree — every tracked file and every untracked one that `.gitignore` does not
   exclude — is copied to a temporary directory and committed there as the baseline, with an
   empty repository beside it as `origin`, which holds no reserved number;
2. every gate runs once on the baseline, against the baseline as its base, and must be green.
   A gate red before any violation proves nothing about catching one; the self-test fails and
   names it;
3. each case clones the baseline, plants its violation and commits it, then runs its gate
   against the baseline. The case passes when the gate fails *and* its output names what the case
   expects. A gate that fails for another reason has not been shown to catch this violation.

The gates run with this interpreter, from the copy, with the copy's `src/` first on the path, so
that the code they read and import is the copy's, never the checkout's. The commands repeat the
recipes of the `Makefile`; `tests/tools/test_gate_selftest.py` holds the two to the same scripts.

A case whose violation cannot be planted — the file or the passage it needs is gone — fails too,
and says so: the case is then rewritten against the repository as it is now, never dropped
silently.

Where it ends: a gate red under every case is shown to catch these violations, not every
violation of its rules. A rule without a case here is held only by the gate's own tests under
`tests/tools/`. The gates that run a suite of the product — contracts, conformance,
governance, exactness — are not fed a violation here. The contracts carry must-fail examples
and the conformance suite meta-tests of their own; governance and exactness have neither.

Nothing here touches the checkout: every write goes to the temporary directory, which is removed
at the end. The last line is the duration.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The violations below must not be violations of the checkout itself, where the same gates read
# this file. A token a gate looks for anywhere in the repository is therefore assembled here
# rather than spelled out.
NEED = "NEED-"
TODO_OWNER = "TODO" + "(owner)"
ADR = "ADR-"
CREDENTIAL = "TAKTUS_CREDENTIAL_SELFTEST" + "_FILE"


class PlantError(Exception):
    """The violation could not be planted: what it needs is not in the repository any more."""


# --- planting ------------------------------------------------------------------------------------


def read(root: Path, rel: str) -> str:
    path = root / rel
    if not path.is_file():
        raise PlantError(f"{rel} does not exist")
    return path.read_text(encoding="utf-8")


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append(root: Path, rel: str, text: str) -> None:
    write(root, rel, read(root, rel).rstrip("\n") + "\n" + text)


def substitute(root: Path, rel: str, pattern: str, replacement: str, flags: int = 0) -> None:
    """Replace the first match of `pattern` in `rel`; a pattern that matches nothing is a case
    that no longer applies."""
    text = read(root, rel)
    changed, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count == 0:
        raise PlantError(f"{rel}: nothing matches {pattern!r}")
    write(root, rel, changed)


def first(root: Path, pattern: str, contains: str | None = None) -> str:
    """The first file, in sorted order, that matches the glob `pattern` and holds `contains`."""
    for path in sorted(root.glob(pattern)):
        if path.is_file() and (contains is None or contains in path.read_text(encoding="utf-8")):
            return path.relative_to(root).as_posix()
    raise PlantError(f"no file {pattern}" + (f" holds {contains!r}" if contains else ""))


def with_section(root: Path, pattern: str, heading: str) -> str:
    """The first file matching `pattern` with a line that is exactly `heading`."""
    for path in sorted(root.glob(pattern)):
        if path.is_file() and heading in path.read_text(encoding="utf-8").splitlines():
            return path.relative_to(root).as_posix()
    raise PlantError(f"no file {pattern} has the line {heading!r}")


def section_body(root: Path, rel: str, heading: str, body: str) -> None:
    """Replace what stands under `heading`, up to the next heading of its level or above."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = read(root, rel).splitlines(keepends=True)
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip("\n") == heading)
    except StopIteration:
        raise PlantError(f"{rel} has no line {heading!r}") from None
    end = start + 1
    while end < len(lines):
        marks = len(lines[end]) - len(lines[end].lstrip("#"))
        if 0 < marks <= level and lines[end][marks : marks + 1] == " ":
            break
        end += 1
    replaced = [*lines[: start + 1], "\n", *([body + "\n\n"] if body else []), *lines[end:]]
    write(root, rel, "".join(replaced))


def core_module(root: Path) -> str:
    """A module of a component, where the core's rules apply."""
    return first(root, "src/taktus/components/*/__init__.py")


def a_use_case(root: Path, state: str) -> str:
    return first(root, "docs/usecases/*/UC-*.md", f"\nstate: {state}\n")


def a_tool_row_swap(root: Path) -> None:
    rel = "tools/README.md"
    lines = read(root, rel).splitlines(keepends=True)
    rows = [i for i, line in enumerate(lines) if line.startswith("| `")]
    if len(rows) < 2:
        raise PlantError(f"{rel} has fewer than two rows of tools")
    a, b = rows[0], rows[1]
    lines[a], lines[b] = lines[b], lines[a]
    write(root, rel, "".join(lines))


def an_open_request(root: Path) -> str:
    return with_section(root, "docs/decisions/open/DEC-*.md", "## 6. What is blocked")


def a_duplicate_record(root: Path) -> None:
    rel = first(root, "docs/decisions/DEC-*.md")
    number = Path(rel).name[4:8]
    write(root, f"docs/decisions/DEC-{number}-selftest-duplicate.md", read(root, rel))


def a_record_without_reservation(root: Path) -> None:
    rel = first(root, "docs/decisions/DEC-*.md", "## Outcome")
    text = re.sub(r"^# DEC-\d{4}", "# DEC-9990", read(root, rel), count=1)
    write(root, "docs/decisions/DEC-9990-selftest-unreserved.md", text)


def a_blocking_request(root: Path) -> None:
    substitute(
        root, an_open_request(root), r"\*\*Category:\*\* NON-BLOCKING", "**Category:** BLOCKING"
    )
    write(root, "selftest-description.md", DESCRIPTION)


def a_gate_weakened_notice(root: Path) -> str:
    return with_section(root, "docs/decisions/NTC-*.md", "## 5. Why the gate had no value")


def an_open_need(root: Path) -> str:
    return with_section(root, "docs/decisions/open/NEED-*.md", "## 5. What it must never be")


def a_promising_adr(root: Path) -> str:
    return with_section(root, "docs/adr/ADR-*.md", "## Where this promise ends")


def a_requirement_and_its_code(root: Path) -> None:
    rel = first(root, "docs/usecases/run/UC-*.md", "\nstate: specified\n")
    substitute(
        root,
        rel,
        r"^## 1\. What must be achieved\n\n",
        "## 1. What must be achieved\n\nThe self-test changed this requirement.\n\n",
        flags=re.MULTILINE,
    )
    append(root, "src/taktus/components/run/__init__.py", "# changed beside its requirement\n")


def a_verified_use_case_with_a_red_test(root: Path) -> None:
    test = "tests/tools/test_selftest_red.py"
    write(
        root,
        test,
        '"""A test that fails, named by a use case the self-test marks verified."""\n\n\n'
        "def test_red() -> None:\n    raise AssertionError('red on purpose')\n",
    )
    rel = a_use_case(root, "specified")
    substitute(root, rel, r"^state: specified$", "state: verified", flags=re.MULTILINE)
    substitute(root, rel, r"^tests: .*$", f"tests: [{test}::test_red]", flags=re.MULTILINE)


def a_use_case_whose_adr_moved(root: Path) -> None:
    rel = first(root, "docs/usecases/*/UC-*.md", "adrs: {ADR-")
    found = re.search(r"adrs: \{(ADR-\d{4}):", read(root, rel))
    if found is None:
        raise PlantError(f"{rel} records no ADR")
    adr = first(root, f"docs/adr/{found.group(1)}-*.md")
    substitute(
        root,
        adr,
        r"^## Context\n",
        "## Context\nThe self-test moved this ADR under its use cases.\n",
        flags=re.MULTILINE,
    )


def no_principle_served(root: Path) -> None:
    """No use case serves principle 14 any more."""
    planted = False
    for path in sorted(root.glob("docs/usecases/*/UC-*.md")):
        text = path.read_text(encoding="utf-8")
        changed = re.sub(
            r"^(serves: \[)(.*)\]$",
            lambda m: (
                m.group(1)
                + ", ".join(p for p in m.group(2).split(", ") if p.strip() != "P14")
                + "]"
            ),
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if changed != text:
            planted = True
            path.write_text(changed, encoding="utf-8")
    if not planted:
        raise PlantError("no use case serves P14")


def a_process_name_in_the_product(root: Path) -> None:
    rel = first(root, "blueprints/*/processes/*.yaml")
    found = re.search(r"^id: *(\S+)", read(root, rel), re.MULTILINE)
    if found is None:
        raise PlantError(f"{rel} declares no id")
    append(root, "src/taktus/composition/__init__.py", f'SELFTEST = "{found.group(1)}"\n')


def a_model(root: Path, name: str, config: str, fields: str) -> None:
    """A value type of a component's domain model, planted where the architecture reads it."""
    write(
        root,
        f"src/taktus/components/reporting/domain/model/selftest_{name}.py",
        f'"""A model the gate self-test planted."""\n\n'
        "from pydantic import BaseModel, ConfigDict\n\n\n"
        f"class Selftest{name.title()}(BaseModel):\n"
        f"    model_config = ConfigDict({config})\n\n"
        f"{fields}",
    )


def a_worker_importing_the_core(root: Path) -> None:
    append(root, first(root, "workers/*/*.py"), "import taktus.components  # noqa: E402,F401\n")


# --- the gates and their cases -------------------------------------------------------------------

# Placeholders: {python} this interpreter, {bin} its directory, {base} the baseline commit,
# {root} the copy.
GATES: dict[str, tuple[tuple[str, ...], ...]] = {
    "gate-arch": (
        ("{bin}/lint-imports",),
        ("{python}", "tools/gate.py", "architecture", "tests/architecture"),
    ),
    "gate-docs": (("{python}", "tools/checkdocs.py", "--base", "{base}"),),
    "gate-decisions": (("{python}", "tools/check_decisions.py", "--base", "{base}"),),
    "gate-adrs": (("{python}", "tools/check_adrs.py"),),
    "gate-status": (("{python}", "tools/check_status.py", "--base", "{base}"),),
    "gate-vision": (("{python}", "tools/check_vision.py"),),
    "gate-usecases": (("{python}", "tools/check_usecases.py", "--base", "{base}"),),
}

# A pull request description with the sections every description carries (ADR-0017 §7).
DESCRIPTION = """Part of #395.

## What this is about
The self-test's description.

## Decisions required
None

## Behaviour changes
None

## What was done
Nothing.

## Why this way
To be checked.

## What to check
That the gate reads this.

## Notes
None.

## Needed from the owner
Nothing.
"""


@dataclass(frozen=True)
class Case:
    """One deliberate violation of one gate."""

    gate: str
    what: str
    plant: Callable[[Path], None]
    expect: str  # a fragment the gate's output must hold: it failed for this violation
    args: tuple[str, ...] = ()  # appended to the gate's last command


def _description(text: str) -> Callable[[Path], None]:
    def plant(root: Path) -> None:
        write(root, "selftest-description.md", text)

    return plant


def _cases() -> tuple[Case, ...]:
    body = ("--pr-body", "{root}/selftest-description.md")
    return (
        # --- documentation freshness --------------------------------------------------------
        Case(
            "gate-docs",
            "tools/README.md lists two tools out of alphabetical order",
            a_tool_row_swap,
            "keep the table alphabetical",
        ),
        Case(
            "gate-docs",
            "a contract's schema changes and its README does not",
            lambda r: append(r, first(r, "contracts/*/v*/*.json"), "\n"),
            "changes a contract",
        ),
        Case(
            "gate-docs",
            "a tool changes and tools/README.md does not",
            lambda r: append(r, "tools/gate.py", "# changed\n"),
            "changes a tool or a make target",
        ),
        Case(
            "gate-docs",
            "a component changes and no architecture document or ADR does",
            lambda r: append(r, core_module(r), "# changed\n"),
            "changes a component",
        ),
        Case(
            "gate-docs",
            "a deployment changes and its README does not",
            lambda r: append(r, first(r, "deploy/docker/*.sh"), "# changed\n"),
            "changes a deployment",
        ),
        # --- the decision register ----------------------------------------------------------
        Case(
            "gate-decisions",
            "an open decision request loses a section",
            lambda r: substitute(r, an_open_request(r), r"^## 6\. What is blocked\n", "", re.M),
            "missing section(s): `## 6. What is blocked`",
        ),
        Case(
            "gate-decisions",
            "an open decision request does not name the sources it checked",
            lambda r: substitute(
                r,
                first(r, "docs/decisions/open/DEC-*.md", "**Sources checked:**"),
                r"\*\*Sources checked:\*\*",
                "Sources:",
            ),
            "names no `**Sources checked:**`",
        ),
        Case(
            "gate-decisions",
            "an open decision request recommends two options",
            lambda r: substitute(
                r,
                first(r, "docs/decisions/open/DEC-*.md", "(recommended)"),
                r"^(### Option [A-Z] — (?:(?!\(recommended\)).)*)$",
                r"\1 (recommended)",
                re.M,
            ),
            "recommended",
        ),
        Case(
            "gate-decisions",
            "a section of an open decision request keeps a placeholder",
            lambda r: section_body(r, an_open_request(r), "## 6. What is blocked", "TBD"),
            "keeps a placeholder",
        ),
        Case(
            "gate-decisions",
            "a decided record has no outcome",
            lambda r: substitute(
                r, first(r, "docs/decisions/DEC-*.md", "## Outcome"), r"^## Outcome$", "", re.M
            ),
            "`## Outcome` is missing",
        ),
        Case(
            "gate-decisions",
            "two records carry one number",
            a_duplicate_record,
            "selftest-duplicate",
        ),
        Case(
            "gate-decisions",
            "a record is added without a number reserved on the remote",
            a_record_without_reservation,
            "without a reservation",
        ),
        Case(
            "gate-decisions",
            "the register's README stores a row of the index",
            lambda r: append(
                r,
                "docs/decisions/README.md",
                "| [DEC-0001](DEC-0001-contract-identity.md) | Contract identity |\n",
            ),
            "stores a row of the index",
        ),
        Case(
            "gate-decisions",
            "a gate-weakened notice does not say why the gate had no value",
            lambda r: substitute(
                r,
                a_gate_weakened_notice(r),
                r"^## 5\. Why the gate had no value$",
                "## 5. Afterword",
                re.M,
            ),
            "missing section(s): `## 5. Why the gate had no value`",
        ),
        Case(
            "gate-decisions",
            "a notice names a mode entry that does not exist",
            lambda r: substitute(
                r,
                first(r, "docs/decisions/NTC-*.md", "**Mode entry:** M2."),
                r"\*\*Mode entry:\*\* M2\.\d+",
                "**Mode entry:** M2.99",
            ),
            "M2.99 is not an entry",
        ),
        Case(
            "gate-decisions",
            "a needs request does not say what it must never be",
            lambda r: substitute(
                r, an_open_need(r), r"^## 5\. What it must never be$", "## 5. Remarks", re.M
            ),
            "missing section(s): `## 5. What it must never be`",
        ),
        Case(
            "gate-decisions",
            "the code reads a credential CREDENTIALS.md does not describe",
            lambda r: append(
                r, "src/taktus/composition/__init__.py", f'SELFTEST = "{CREDENTIAL}"\n'
            ),
            f"{CREDENTIAL} is read by",
        ),
        Case(
            "gate-decisions",
            "a document names a needs request that has no file",
            lambda r: append(r, "docs/roadmap.md", f"See {NEED}9998.\n"),
            f"{NEED}9998 has no file",
        ),
        Case(
            "gate-decisions",
            "an action left to the owner names no open record",
            lambda r: append(r, "docs/roadmap.md", f"{TODO_OWNER}: the self-test.\n"),
            "names no open needs request or decision request",
        ),
        Case(
            "gate-decisions",
            "a pull request description lacks the section What to check",
            _description(DESCRIPTION.replace("## What to check\nThat the gate reads this.\n", "")),
            "no `## What to check`",
            body,
        ),
        Case(
            "gate-decisions",
            "a behaviour change is not stated as old, new and reason",
            _description(
                DESCRIPTION.replace(
                    "## Behaviour changes\nNone\n", "## Behaviour changes\n- It does more now.\n"
                )
            ),
            "not a behaviour change",
            body,
        ),
        Case(
            "gate-decisions",
            "a pull request title is not a Conventional Commit",
            lambda r: None,
            "is not in the Conventional Commits form",
            ("--pr-title", "Add the self-test"),
        ),
        Case(
            "gate-decisions",
            "a pull request with a BLOCKING decision open is ready",
            a_blocking_request,
            "stays a draft until the answer is recorded",
            (*body, "--draft", "false"),
        ),
        # --- the ADRs -----------------------------------------------------------------------
        Case(
            "gate-adrs",
            "an ADR that promises does not say where the promise ends",
            lambda r: substitute(
                r, a_promising_adr(r), r"^## Where this promise ends$", "## Limits", re.M
            ),
            "without `## Where this promise ends`",
        ),
        Case(
            "gate-adrs",
            "the boundary of a promise is a bare pointer to another document",
            lambda r: section_body(
                r, a_promising_adr(r), "## Where this promise ends", "See ADR-0001."
            ),
            "is a pointer to another document",
        ),
        Case(
            "gate-adrs",
            "the boundary of a promise is not the last section",
            lambda r: append(r, a_promising_adr(r), "\n## Afterword\n\nMore after the boundary.\n"),
            "is not the last section",
        ),
        Case(
            "gate-adrs",
            "an ADR is named that has no file",
            lambda r: append(r, "docs/roadmap.md", f"As {ADR}9997 says.\n"),
            f"names {ADR}9997, and no",
        ),
        Case(
            "gate-adrs",
            "an ADR's first line is not its title",
            lambda r: substitute(
                r, first(r, "docs/adr/ADR-0001-*.md"), r"^# ADR-0001 — ", "# ADR 1: ", re.M
            ),
            "first line is not `# ADR-NNNN — Title`",
        ),
        Case(
            "gate-adrs",
            "docs/adr/README.md stores a row of the index",
            lambda r: append(r, "docs/adr/README.md", "| [0001](ADR-0001.md) | Language |\n"),
            "stores rows of the index",
        ),
        # --- the status ---------------------------------------------------------------------
        Case(
            "gate-status",
            "docs/status.md stores a date every pull request rewrites",
            lambda r: substitute(
                r, "docs/status.md", r"^# Status\n", "# Status\n\n**As of:** 2026-10-23\n", re.M
            ),
            "`**As of:**` is a line every pull request rewrites",
        ),
        Case(
            "gate-status",
            "docs/status.md stores the owner's list instead of pointing at make status",
            lambda r: substitute(
                r,
                "docs/status.md",
                r"^(## 3\. Needed from the owner\n)",
                rf"\1\n| {NEED}0021 | A wiki for the guides | 2026-11-14 | account | #199 |\n",
                re.M,
            ),
            "section 3 stores the list",
        ),
        Case(
            "gate-status",
            "docs/status.md loses a section",
            lambda r: substitute(r, "docs/status.md", r"^## 4\. Blocked$", "## 4. Stuck", re.M),
            "missing section(s): `## 4. Blocked`",
        ),
        Case(
            "gate-status",
            "the roadmap changes and the status does not",
            lambda r: append(r, "docs/roadmap.md", "A milestone item the self-test added.\n"),
            "not touched, although the state of the project changed",
        ),
        Case(
            "gate-status",
            "an entry of a milestone's status is added at its end, out of order",
            lambda r: append(
                r,
                first(r, "docs/status/0.*.md", "\n**"),
                "\n**Aaa, the self-test's entry** (#395). Out of order.\n",
            ),
            "is out of place",
        ),
        # --- the vision ---------------------------------------------------------------------
        Case(
            "gate-vision",
            "a principle's title differs from the one CLAUDE.md gives it",
            lambda r: substitute(
                r, "docs/vision/principles.md", r"^## 1 — .*$", "## 1 — An orchestrator", re.M
            ),
            "titled 'An orchestrator'",
        ),
        Case(
            "gate-vision",
            "a principle forbids nothing",
            lambda r: substitute(
                r, "docs/vision/principles.md", r"\*\*Forbids\.\*\*", "**Allows.**"
            ),
            "no **Forbids.**",
        ),
        Case(
            "gate-vision",
            "a file of the vision is not listed in its README",
            lambda r: write(r, "docs/vision/selftest.md", "# Self-test\n\nUnlisted.\n"),
            "does not list selftest.md",
        ),
        Case(
            "gate-vision",
            "the market picture loses its staleness warning",
            lambda r: substitute(r, "docs/vision/market.md", r"Stale by construction", "Current"),
            "does not open with `> **Stale by construction",
        ),
        Case(
            "gate-vision",
            "a principle is served by no use case",
            no_principle_served,
            "no use case serves it",
        ),
        # --- the use cases ------------------------------------------------------------------
        Case(
            "gate-usecases",
            "a use case has no verification condition",
            lambda r: section_body(r, a_use_case(r, "specified"), "## 2. How it is verified", ""),
            "`## 2. How it is verified` is empty",
        ),
        Case(
            "gate-usecases",
            "a built use case names a test that does not exist",
            lambda r: substitute(
                r,
                a_use_case(r, "built"),
                r"^tests: \[",
                "tests: [tests/tools/test_lanes.py::test_the_self_test_wrote_this, ",
                re.M,
            ),
            "no test function `test_the_self_test_wrote_this`",
        ),
        Case(
            "gate-usecases",
            "a verified use case names a test that fails",
            a_verified_use_case_with_a_red_test,
            "state `verified`, but 1 run: 1 failed",
        ),
        Case(
            "gate-usecases",
            "an ADR moves under a use case that is not checked against it again",
            a_use_case_whose_adr_moved,
            "changed after this use case was checked against it",
        ),
        Case(
            "gate-usecases",
            "a requirement changes in the pull request that implements it",
            a_requirement_and_its_code,
            "and its implementation too",
        ),
        # --- the architecture ---------------------------------------------------------------
        Case(
            "gate-arch",
            "one component imports another",
            lambda r: append(
                r,
                "src/taktus/components/run/__init__.py",
                "import taktus.components.reporting  # noqa: E402,F401\n",
            ),
            "Components never import each other BROKEN",
        ),
        Case(
            "gate-arch",
            "one component writes another's aggregate through a repository",
            lambda r: write(
                r,
                "src/taktus/components/reporting/application/service/selftest_write.py",
                '"""A write across a component boundary, planted by the gate self-test."""\n\n'
                "from taktus.components.run.domain.model.run import Run\n"
                "from taktus.ports.persistence import Repository\n\n\n"
                "async def overwrite(runs: Repository[Run], run: Run) -> None:\n"
                '    await runs.put("default", run)\n',
            ),
            "Components never import each other BROKEN",
        ),
        Case(
            "gate-arch",
            "the core imports a technology",
            lambda r: append(r, core_module(r), "import sqlalchemy  # noqa: E402,F401\n"),
            "The core imports no technology BROKEN",
        ),
        Case(
            "gate-arch",
            "a product's name stands in a comment of the core",
            lambda r: append(r, core_module(r), "# works best with redis\n"),
            "test_no_product_name_in_the_core",
        ),
        Case(
            "gate-arch",
            "the core reads the clock itself",
            lambda r: append(
                r,
                core_module(r),
                "from datetime import datetime  # noqa: E402\n\n\n"
                "def selftest_now() -> datetime:\n    return datetime.now()\n",
            ),
            "test_time_identifiers_and_randomness_come_from_ports",
        ),
        Case(
            "gate-arch",
            "a module does not say what it is",
            lambda r: write(r, "src/taktus/components/run/selftest_undocumented.py", "X = 1\n"),
            "test_every_module_has_a_docstring",
        ),
        Case(
            "gate-arch",
            "a tracked path belongs to no lane",
            lambda r: write(r, "selftest-unclaimed.cfg", "unclaimed = true\n"),
            "selftest-unclaimed.cfg",
        ),
        Case(
            "gate-arch",
            "a worker imports the control plane",
            a_worker_importing_the_core,
            "test_workers_import_nothing_from_the_control_plane",
        ),
        Case(
            "gate-arch",
            "the product names a process of the project's own tenant",
            a_process_name_in_the_product,
            "test_no_string_of_the_product_names_the_project",
        ),
        Case(
            "gate-arch",
            "a domain model can be changed after it was made",
            lambda r: a_model(r, "open", 'frozen=False, extra="forbid"', "    value: str\n"),
            "is not frozen",
        ),
        Case(
            "gate-arch",
            "a value type holds a figure under a person's name",
            lambda r: a_model(
                r, "score", 'frozen=True, extra="forbid"', "    person: str\n    score: int\n"
            ),
            "principle 14 forbids it",
        ),
    )


CASES = _cases()


# --- running -------------------------------------------------------------------------------------


@dataclass
class Outcome:
    case: Case | None  # None: the gate on the baseline
    gate: str
    passed: bool
    why: str
    output: str = field(repr=False, default="")


def git(cwd: Path, *args: str) -> str:
    # A fixed executable and arguments assembled here; the paths are the self-test's own.
    result = subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=gate-selftest", "-c", "user.email=selftest@invalid", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def baseline(source: Path, into: Path) -> str:
    """Copy the working tree of `source` to `into`, commit it, and return the commit."""
    listed = git(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    copy = into / "tree"
    for rel in sorted(set(filter(None, listed.split("\0")))):
        origin = source / rel
        if origin.is_file() and not origin.is_symlink():
            target = copy / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        elif origin.is_symlink():
            target = copy / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.readlink(origin))
    remote = into / "remote.git"
    git(into, "init", "-q", "--bare", str(remote))
    git(copy, "init", "-q", "-b", "main")
    git(copy, "remote", "add", "origin", str(remote))
    git(copy, "add", "-A")
    git(copy, "commit", "-q", "--no-verify", "-m", "baseline")
    return git(copy, "rev-parse", "HEAD").strip()


def commands(gate: str, root: Path, base: str, args: Sequence[str]) -> list[list[str]]:
    values = {
        "python": sys.executable,
        "bin": str(Path(sys.executable).parent),
        "base": base,
        "root": str(root),
    }
    planned = [list(command) for command in GATES[gate]]
    planned[-1].extend(args)
    return [[part.format(**values) for part in command] for command in planned]


def run_gate(gate: str, root: Path, base: str, args: Sequence[str] = ()) -> tuple[bool, str]:
    """Run every command of the gate in `root`; green only if each one exits 0."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root / "src"), env.get("PYTHONPATH")]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    output: list[str] = []
    green = True
    for command in commands(gate, root, base, args):
        # This interpreter and the gates' own scripts, from the copy; nothing from input.
        result = subprocess.run(  # noqa: S603
            command, cwd=root, env=env, capture_output=True, text=True, check=False
        )
        output.append(result.stdout + result.stderr)
        green = green and result.returncode == 0
    return green, "\n".join(output)


def complaints(output: str) -> str:
    """The output without the lines in which a gate reports a check that passed (`  ok   …`):
    a fragment of a passing line does not show that the gate failed for the violation."""
    return "\n".join(line for line in output.splitlines() if not OK_LINE.match(line))


OK_LINE = re.compile(r"^\s*ok\s")


CLONING = threading.Lock()


def clone(source: Path, target: Path) -> None:
    """Clone the baseline, one clone at a time: a local clone copies the object files, and two
    run together failed on a runner to copy one ("No such file or directory"). A clone that
    fails all the same is made again through the transport, which packs instead of copying."""
    with CLONING:
        try:
            git(source.parent, "clone", "-q", str(source), str(target))
        except RuntimeError:
            shutil.rmtree(target, ignore_errors=True)
            git(source.parent, "clone", "-q", "--no-local", str(source), str(target))


def run_case(case: Case, work: Path, index: int, base: str) -> Outcome:
    root = work / f"case-{index:02d}"
    clone(work / "tree", root)
    try:
        case.plant(root)
    except PlantError as error:
        return Outcome(case, case.gate, False, f"the violation could not be planted: {error}")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "--allow-empty", "-m", case.what)
    green, output = run_gate(case.gate, root, base, case.args)
    shutil.rmtree(root, ignore_errors=True)
    if green:
        return Outcome(case, case.gate, False, "the gate stayed green", output)
    if case.expect not in complaints(output):
        why = f"the gate failed, but no complaint of its output names {case.expect!r}"
        return Outcome(case, case.gate, False, why, output)
    return Outcome(case, case.gate, True, "caught", output)


def run(cases: Sequence[Case], source: Path = ROOT, workers: int | None = None) -> list[Outcome]:
    """Every gate the cases name on the baseline, then every case; one Outcome each."""
    gates = sorted({case.gate for case in cases})
    workers = workers or max(1, min(8, (os.cpu_count() or 2) // 2))
    with tempfile.TemporaryDirectory(prefix="gate-selftest-") as tmp:
        work = Path(tmp)
        base = baseline(source, work)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            clean = list(pool.map(lambda g: (g, run_gate(g, work / "tree", base)), gates))
            outcomes = [
                Outcome(
                    None,
                    gate,
                    green,
                    "green before any violation"
                    if green
                    else "red before any violation: a gate red already proves nothing",
                    output,
                )
                for gate, (green, output) in clean
            ]
            usable = [c for c in cases if dict(clean)[c.gate][0]]
            outcomes += list(
                pool.map(lambda pair: run_case(pair[1], work, pair[0], base), enumerate(usable))
            )
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gate", action="append", choices=sorted(GATES), help="only this gate")
    parser.add_argument("--list", action="store_true", help="print every case and run nothing")
    parser.add_argument("--verbose", action="store_true", help="print a failing gate's output")
    args = parser.parse_args(argv)
    cases = [c for c in CASES if not args.gate or c.gate in args.gate]
    if args.list:
        for case in cases:
            print(f"{case.gate}: {case.what}")
        return 0
    started = time.monotonic()
    outcomes = run(cases)
    failed = 0
    for outcome in outcomes:
        what = outcome.case.what if outcome.case else "the baseline"
        mark = "ok  " if outcome.passed else "FAIL"
        print(f"  {mark} {outcome.gate}: {what} — {outcome.why}")
        if not outcome.passed:
            failed += 1
            if args.verbose and outcome.output:
                print("\n".join(f"       | {line}" for line in outcome.output.splitlines()[-40:]))
    print()
    duration = f"{time.monotonic() - started:.1f}s"
    caught = sum(1 for o in outcomes if o.case and o.passed)
    print(
        f"gate-selftest: {caught} of {len(cases)} violations caught, {failed} failed in {duration}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
