# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Print the tree of `src/taktus`, each package and module with the first sentence it states.

Runs as `make tree`. Standard library only.

The tree of `docs/architecture/project-structure.md` §2 named every module with a line of
explanation. Every pull request that added a module extended one of a few long lines there, and
two such pull requests conflicted (#392: six conflicts in the replay of 100 merges). The
explanation now lives where the module is, as its docstring, and this tool prints the tree from
the repository: a package by its `__init__.py`, a module by its own docstring, the first
sentence of each. `tests/architecture` fails a module without one.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path("src") / "taktus"
SENTENCE = re.compile(r"(.+?[.!?])(?:\s|$)", re.DOTALL)


def first_sentence(path: Path) -> str:
    """The first sentence of a module's docstring, on one line; empty without one."""
    try:
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    except SyntaxError:
        return ""
    paragraph = " ".join(docstring.split("\n\n")[0].split())
    found = SENTENCE.match(paragraph)
    return found.group(1) if found else paragraph


def entries(directory: Path) -> list[Path]:
    children = [
        p
        for p in directory.iterdir()
        if not p.name.startswith((".", "__pycache__"))
        and (
            (p.is_dir() and any(p.rglob("*.py"))) or (p.suffix == ".py" and p.name != "__init__.py")
        )
    ]
    return sorted(children, key=lambda p: (p.is_file(), p.name))


def lines(directory: Path, prefix: str = "") -> list[str]:
    out: list[str] = []
    children = entries(directory)
    for position, child in enumerate(children):
        last = position == len(children) - 1
        branch = "└── " if last else "├── "
        name = child.name + ("/" if child.is_dir() else "")
        explained = child / "__init__.py" if child.is_dir() else child
        sentence = first_sentence(explained) if explained.exists() else ""
        head = f"{prefix}{branch}{name}"
        out.append(f"{head:<44} # {sentence}" if sentence else head)
        if child.is_dir():
            out += lines(child, prefix + ("    " if last else "│   "))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="the repository's root")
    parser.add_argument("path", nargs="?", default=str(SOURCE), help="the directory to print")
    args = parser.parse_args(argv)
    base = args.root / args.path
    if not base.is_dir():
        print(f"tree: {args.path} is not a directory", file=sys.stderr)
        return 1
    print(f"{args.path}/")
    print("\n".join(lines(base)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
