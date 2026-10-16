"""Every module under `src/taktus` states what it is in its docstring (#392).

The tree of the source is printed from these docstrings by `make tree` (`tools/tree.py`),
instead of being kept by hand in `docs/architecture/project-structure.md`, where every new
module extended one of a few long lines and two pull requests conflicted on them. A module
without a docstring would be a line of the tree without its explanation. A package's
`__init__.py` may stay empty: its directory is explained by its modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src" / "taktus"


def test_every_module_has_a_docstring() -> None:
    missing = [
        str(path.relative_to(SOURCE))
        for path in sorted(SOURCE.rglob("*.py"))
        if path.name != "__init__.py"
        and not ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not missing, f"modules without a docstring: {missing}"
