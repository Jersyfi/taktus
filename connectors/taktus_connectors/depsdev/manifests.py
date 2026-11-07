"""The exact versions a dependency manifest pins, read from its text by its format's own rules.

- **package-lock.json**, npm's lockfile of version 2 or 3: every entry of `packages` but the
  root `""` and a `link`, its name the part after the last `node_modules/` of its key, its
  `version`, and `dev`. Version 1 has no `packages`: its `dependencies`, nested, are read.
- **uv.lock**, TOML: every `[[package]]` with a `name` and a `version` whose `source` is a
  registry, so that the project itself and a path or a repository dependency are left out.
- **requirements.txt**: every line `name==version`, an extra and an environment marker set
  aside. A line that pins no exact version is unpinned: an index answers a version, not a range.

The name of a PyPI package is normalised as PEP 503 states, as the index expects it. A text that
is not the format it claims is refused: nothing is guessed from it.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any

FORMATS = ("package-lock.json", "uv.lock", "requirements.txt")
PINNED = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*===?\s*([A-Za-z0-9][A-Za-z0-9._+!-]*)\s*$"
)
NAMED = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class NotTheFormat(ValueError):
    """The text is not a manifest of the format it names."""


@dataclass(frozen=True)
class Pinned:
    system: str
    name: str
    version: str
    dev: bool = False


def normalised(name: str) -> str:
    """A PyPI name as PEP 503 normalises it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _npm(text: str) -> tuple[list[Pinned], list[str]]:
    try:
        document = json.loads(text)
    except ValueError as error:
        raise NotTheFormat("the text is not JSON") from error
    if not isinstance(document, dict):
        raise NotTheFormat("the lockfile is not an object")
    found: list[Pinned] = []
    packages = document.get("packages")
    if isinstance(packages, dict):
        for key, entry in packages.items():
            if key == "" or not isinstance(entry, dict) or entry.get("link"):
                continue
            name = key.rsplit("node_modules/", 1)[-1]
            version = entry.get("version")
            if name and isinstance(version, str):
                found.append(Pinned("NPM", name, version, bool(entry.get("dev"))))
        return found, []
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, dict):
        raise NotTheFormat("the lockfile has neither packages nor dependencies")

    def walk(level: dict[str, Any]) -> None:
        for name, entry in level.items():
            if not isinstance(entry, dict):
                continue
            version = entry.get("version")
            if isinstance(version, str) and not version.startswith(("file:", "link:")):
                found.append(Pinned("NPM", name, version, bool(entry.get("dev"))))
            nested = entry.get("dependencies")
            if isinstance(nested, dict):
                walk(nested)

    walk(dependencies)
    return found, []


def _uv(text: str) -> tuple[list[Pinned], list[str]]:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise NotTheFormat("the text is not TOML") from error
    packages = document.get("package")
    if not isinstance(packages, list):
        raise NotTheFormat("the lockfile has no packages")
    found: list[Pinned] = []
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        name, version, source = entry.get("name"), entry.get("version"), entry.get("source")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        if not isinstance(source, dict) or "registry" not in source:
            continue
        found.append(Pinned("PYPI", normalised(name), version))
    return found, []


def _requirements(text: str) -> tuple[list[Pinned], list[str]]:
    found: list[Pinned] = []
    unpinned: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        pinned = PINNED.match(line)
        if pinned is not None:
            found.append(Pinned("PYPI", normalised(pinned.group(1)), pinned.group(2)))
            continue
        named = NAMED.match(line)
        if named is None:
            raise NotTheFormat("a line is not a requirement")
        unpinned.append(normalised(named.group(1)))
    return found, unpinned


def pinned(format: str, text: str) -> tuple[list[Pinned], list[str]]:
    """The exact versions the manifest pins, each once, and the names it leaves unpinned."""
    reader = {"package-lock.json": _npm, "uv.lock": _uv, "requirements.txt": _requirements}
    found, unpinned = reader[format](text)
    unique: dict[tuple[str, str, str], Pinned] = {}
    for entry in found:
        key = (entry.system, entry.name, entry.version)
        if key not in unique or (unique[key].dev and not entry.dev):
            unique[key] = entry
    return sorted(unique.values(), key=lambda p: (p.name, p.version)), sorted(set(unpinned))
