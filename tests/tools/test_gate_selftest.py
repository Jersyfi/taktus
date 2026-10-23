"""`make gate-selftest` fails when a gate stays green under a violation (ADR-0096 §6, #395).

The self-test's own cases run in `make gate-selftest`. Here: that it covers every
documentation, register and architecture gate, that it runs each gate as the `Makefile` does,
and that it fails a violation the gate does not catch, one it cannot plant, and one the gate
fails for another reason.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import gate_selftest  # noqa: E402 — a script under tools/, found through the line above

# The documentation, register and architecture gates (ADR-0096 §6, #395).
SELFTESTED = {
    "gate-arch",
    "gate-docs",
    "gate-decisions",
    "gate-adrs",
    "gate-status",
    "gate-vision",
    "gate-usecases",
}


def recipe(target: str) -> list[str]:
    """The command lines of a `Makefile` target."""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    found = re.search(rf"^{re.escape(target)}:.*\n((?:\t.*\n)+)", text, re.MULTILINE)
    assert found is not None, f"the Makefile has no target {target}"
    return [line.strip() for line in found.group(1).splitlines()]


def test_every_documentation_register_and_architecture_gate_has_a_case() -> None:
    assert set(gate_selftest.GATES) == SELFTESTED
    assert {case.gate for case in gate_selftest.CASES} == SELFTESTED


@pytest.mark.parametrize("gate", sorted(SELFTESTED))
def test_a_gate_runs_as_its_make_target_runs_it(gate: str) -> None:
    lines = recipe(gate)
    commands = gate_selftest.GATES[gate]
    assert len(commands) == len(lines), f"{gate}: the Makefile runs {lines}"
    for command, line in zip(commands, lines, strict=True):
        words = [w.removeprefix("{bin}/") for w in command if w not in ("{python}", "{base}")]
        if "--base" in words:
            words.remove("--base")
            assert "$(if $(BASE),--base $(BASE))" in line, f"{gate}: {line} takes no base"
        assert " ".join(words) in line, f"{gate}: {line} does not run {' '.join(words)}"


def test_the_complaints_leave_out_what_passed() -> None:
    output = "  ok   a check named X\n  FAIL docs/x.md\n       names Y"
    assert "X" not in gate_selftest.complaints(output)
    assert "names Y" in gate_selftest.complaints(output)


def test_a_section_body_is_replaced_up_to_the_next_heading(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# T\n\n## 1. A\n\nold\n\n### sub\n\nx\n\n## 2. B\n\nkept\n")
    gate_selftest.section_body(tmp_path, "a.md", "## 1. A", "new")
    assert (tmp_path / "a.md").read_text() == "# T\n\n## 1. A\n\nnew\n\n## 2. B\n\nkept\n"


def test_a_violation_the_gate_misses_or_that_cannot_be_planted_fails_the_self_test() -> None:
    def gone(root: Path) -> None:
        raise gate_selftest.PlantError("docs/gone.md does not exist")

    adr = next(c for c in gate_selftest.CASES if c.gate == "gate-adrs")
    cases = [
        gate_selftest.Case("gate-adrs", "nothing at all", lambda root: None, "anything"),
        gate_selftest.Case("gate-adrs", "a passage that is gone", gone, "anything"),
        gate_selftest.Case("gate-adrs", adr.what, adr.plant, "a complaint it never makes"),
        adr,
    ]
    outcomes = gate_selftest.run(cases, workers=2)
    by_what = {o.case.what if o.case else "baseline": o for o in outcomes}
    assert by_what["baseline"].passed
    assert not by_what["nothing at all"].passed
    assert by_what["nothing at all"].why == "the gate stayed green"
    assert not by_what["a passage that is gone"].passed
    assert "could not be planted" in by_what["a passage that is gone"].why
    misnamed = [o for o in outcomes if o.case and o.case.expect == "a complaint it never makes"]
    assert not misnamed[0].passed
    assert "no complaint" in misnamed[0].why
    assert [o.passed for o in outcomes if o.case is adr] == [True]
