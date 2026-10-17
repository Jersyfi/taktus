# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""The section a pull request description ends with, printed only for a description that passes.

P-03's coding worker runs this as the command after the work, in its workspace — the tree the
branch will carry — with the agent's summary on its standard input (ADR-0101):

    python3 tools/describe.py < summary

It prints the section the repository generates, `tools/check_status.py --print`, as before. First
it puts the summary and that section together as P-03 does — the summary, then the section under
`## Needed from the owner` — and runs the `description` check on the result,
`tools/check_decisions.py --pr-body`, on the checks that read the description
(`--description-only`): the rest of the register is `make gate-decisions`, which the pipeline
runs on the branch before P-03 opens the pull request. A description the check fails prints
nothing on standard output, the check's failures on standard error, the check named last, and
exits 1: the worker then fails the assignment with that line, and the run gives the issue back
naming it, before any pull request is opened (#471). What P-03 puts before the summary — `Closes #N` and its own statement
— carries no heading, so the check reads the same sections in both.

Standard library only, like the two scripts it runs.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADING = "## Needed from the owner"
"""The heading P-03 puts above what `check_status.py --print` printed (its step `closing-section`)."""


def compose(summary: str, block: str) -> str:
    """The description as P-03 composes it, less what comes before the summary."""
    return f"{summary.strip()}\n\n{HEADING}\n\n{block}"


def failures(report: str) -> list[str]:
    """The failures of a report of `check_decisions.py`: each `FAIL what` with its reason, up to
    the explanation after the dash."""
    lines = report.splitlines()
    found: list[str] = []
    for n, line in enumerate(lines):
        if line.strip().startswith("FAIL "):
            why = lines[n + 1].strip() if n + 1 < len(lines) else ""
            found.append(f"{line.strip()[5:]}: {why.split(' — ')[0]}")
    return found


def run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — this repository's own scripts
        [sys.executable, *argv], cwd=ROOT, capture_output=True, text=True, check=False
    )


def main() -> int:
    summary = sys.stdin.read()
    generated = run("tools/check_status.py", "--print")
    if generated.returncode != 0:
        sys.stderr.write(generated.stdout + generated.stderr)
        return generated.returncode
    block = generated.stdout
    with tempfile.TemporaryDirectory() as directory:
        body = Path(directory) / "description.md"
        body.write_text(compose(summary, block), encoding="utf-8")
        checked = run("tools/check_decisions.py", "--pr-body", str(body), "--description-only")
    if checked.returncode != 0:
        found = failures(checked.stdout) or [f"exited with {checked.returncode}"]
        # The worker names the end of what this wrote: the check comes last.
        sys.stderr.write(
            checked.stderr
            + "; ".join(found)
            + " — `tools/check_decisions.py --pr-body` fails the description\n"
        )
        return 1
    sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
