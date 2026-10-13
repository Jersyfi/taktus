"""The Taktus project is one tenant among others, and nothing of it is product (ADR-0092 §4).

The product's code and the chart's default values name none of the project's own: no process
identifier of its bundles, not its repository's path, not its owner's name. What the project
needs of an instance is configuration its operator sets, a bundle of its tenant, or a document
of this repository.

What is read: every string the code can put somewhere — a value, an error message, a help text,
a description — in every module under `src/`, and every value of `deploy/k8s/chart/values.yaml`.
Comments and docstrings are exempt: they explain where a feature came from and set no
behaviour. The names are derived from the repository itself, so that a new process or a new
owner is held without editing this test: the process identifiers from the bundles under
`blueprints/`, the owner from `LICENSE` and `.github/CODEOWNERS`.

Where the test ends (ADR-0092, "Where this promise ends"): it catches names, not a default that
suits the project without naming it.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
VALUES = ROOT / "deploy" / "k8s" / "chart" / "values.yaml"
BUNDLES = ROOT / "blueprints"

PROCESS_NAME = re.compile(r"\b[PS]-\d{2}\b")
"""How the project names its processes in prose: P-03, S-07."""


def process_ids() -> set[str]:
    """Every identifier a bundle of the project's tenant declares (`id:`)."""
    found: set[str] = set()
    for path in BUNDLES.glob("*/processes/*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("id"), str):
            found.add(document["id"])
    return found


def owner() -> tuple[str, str]:
    """The owner's name, from the copyright line, and their handle, from the code owners."""
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
    name = re.fullmatch(r"Copyright \(c\) \d{4} (.+?)\. All rights reserved\.", licence.strip())
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    handle = re.search(r"^\*\s+@(\S+)", owners, re.MULTILINE)
    assert name is not None, "LICENSE names its holder in its first line"
    assert handle is not None, ".github/CODEOWNERS names the owner of every file"
    return name.group(1), handle.group(1)


def forbidden() -> re.Pattern[str]:
    """The project's names, as whole words, case-insensitively."""
    name, handle = owner()
    words = [
        *sorted(process_ids()),
        f"{handle}/taktus",
        handle,
        name,
        name.split()[-1],
    ]
    return re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, words)) + r")(?![\w-])", re.I)


def strings(path: Path) -> Iterator[tuple[int, str]]:
    """Every string constant of a module that is not a docstring or a bare comment string."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    documentation = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in documentation
        ):
            yield node.lineno, node.value


def leaks(text: str, names: re.Pattern[str]) -> list[str]:
    return [m.group(0) for m in (*PROCESS_NAME.finditer(text), *names.finditer(text))]


def scalars(value: object, at: str = "") -> Iterator[tuple[str, str]]:
    """Every key and every scalar value of a YAML document, with where it is."""
    if isinstance(value, dict):
        for key, inner in value.items():
            where = f"{at}.{key}" if at else str(key)
            yield where, str(key)
            yield from scalars(inner, where)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from scalars(inner, f"{at}[{index}]")
    elif value is not None:
        yield at, str(value)


def test_the_names_it_holds_are_found() -> None:
    """A test that derives nothing holds nothing: the bundles and the owner are read."""
    assert {"p03-implementation", "s07-change-in-dialogue"} <= process_ids()
    names = forbidden()
    name, handle = owner()
    for word in (f"{handle}/taktus", handle, name, "s07-change-in-dialogue", "P-03"):
        assert leaks(f"see {word} here", names), word
    assert not leaks("a process named by its operator", names)


def test_no_string_of_the_product_names_the_project() -> None:
    names = forbidden()
    found = [
        f"{path.relative_to(ROOT)}:{line}: {', '.join(sorted(set(hits)))}"
        for path in sorted(SRC.rglob("*.py"))
        for line, text in strings(path)
        if (hits := leaks(text, names))
    ]
    assert not found, (
        "the product names the Taktus project; make it configuration of the project's tenant "
        "(ADR-0092):\n" + "\n".join(found)
    )


def test_no_default_value_of_the_chart_names_the_project() -> None:
    names = forbidden()
    values = yaml.safe_load(VALUES.read_text(encoding="utf-8"))
    found = [
        f"{where}: {', '.join(sorted(set(hits)))}"
        for where, text in scalars(values)
        if (hits := leaks(text, names))
    ]
    assert not found, "the chart's defaults name the Taktus project (ADR-0092):\n" + "\n".join(
        found
    )


@pytest.mark.parametrize(
    "source",
    [
        'raise ValueError("start S-07 instead")',
        'PROCESS = "s07-change-in-dialogue"',
        'help = f"file it in Jersyfi/taktus at {where}"',
    ],
)
def test_a_leak_in_a_string_is_found_and_one_in_a_docstring_is_not(
    source: str, tmp_path: Path
) -> None:
    module = tmp_path / "module.py"
    module.write_text(f'"""Built for P-03 of Jersyfi/taktus."""\n{source}\n', encoding="utf-8")
    found = [text for _, text in strings(module) if leaks(text, forbidden())]
    assert len(found) == 1 and "Built for" not in found[0]
