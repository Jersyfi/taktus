"""The table of tools/README.md lists its tools in alphabetical order, so that two pull requests
that each add a tool land apart (#498).

The check lives in a script under `tools/`; the tests call its function directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import checkdocs  # noqa: E402 — a script under tools/, found through the line above

HEADER = "| Tool | Runs as | Does |\n|---|---|---|\n"


def test_an_alphabetical_table_passes() -> None:
    table = HEADER + "| `backlog.py` | x | y |\n| `Check.py` | x | y |\n| `gate.py` | x | y |\n"
    assert checkdocs.check_tools_table(table) is None


def test_a_row_out_of_order_fails_and_names_it() -> None:
    table = HEADER + "| `gate.py` | x | y |\n| `backlog.py` | x | y |\n"
    failure = checkdocs.check_tools_table(table)
    assert failure is not None
    assert "`backlog.py` after `gate.py`" in failure


def test_the_repositorys_table_is_in_order() -> None:
    assert checkdocs.check_tools_table(checkdocs.TOOLS_README.read_text(encoding="utf-8")) is None
