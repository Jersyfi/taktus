"""`taktusctl bundle check`: process bundles held to registration's rules, without an instance.

It reads each bundle and holds it to what registration holds it to (`parse_bundle`): the shape,
every step's rules, the graph, and the exactness statement (ADR-0113 §4). It needs no wiring, no
database, no login and no network, so that a repository holding bundles can run it in its own
CI. Nothing is stored and nothing is recorded.

Below a directory it also checks every skill under a `skills/` directory: its `SKILL.md` held
to the open format by the catalogue's rule, its name equal to its directory's (ADR-0162 §9).

Three refusals of registration need an instance, and this command does not make them: a step
naming a credential that administers the instance's platform (ADR-0025), a raise of an
autonomy level over the active version (ADR-0039), and a version already registered with
another content.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from taktus.components.catalog.domain.model import InvalidSkill, SkillFile
from taktus.components.catalog.domain.service import skills as rules
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess

bundle = typer.Typer(
    help="Process bundles, without an instance.", no_args_is_help=True, add_completion=False
)

SUFFIXES = (".yaml", ".yml")
NOT_CHECKED = (
    "Not checked without an instance: a credential that administers its platform, "
    "a raise of an autonomy level, a version registered before with another content"
)


@bundle.command("check")
def check(
    paths: Annotated[
        list[Path],
        typer.Argument(
            help="A process bundle, a YAML file; or a directory, whose YAML files below it are "
            "checked, each but one whose top-level `kind` says it is no process (a blueprint).",
            exists=True,
        ),
    ],
) -> None:
    """Hold process bundles to the rules registration holds them to.

    Exit code 0: every bundle would register.

    Exit code 1: a bundle would be refused; the findings say why.

    Exit code 2: a file cannot be read, or no bundle was found.
    """
    checked = refused = unreadable = skipped = 0
    for path, named in _bundles(paths):
        try:
            document = _load(path, named=named)
        except (OSError, yaml.YAMLError, ValueError) as error:
            unreadable += 1
            typer.echo(f"unreadable {path}: {error}")
            continue
        if document is None:
            skipped += 1  # a directory's file that says it is no process bundle
            continue
        checked += 1
        try:
            version = parse_bundle(document)
        except InvalidProcess as error:
            refused += 1
            typer.echo(f"refused    {path}")
            for finding in error.findings:
                typer.echo(f"  - {finding}")
            continue
        typer.echo(f"ok         {path}  {version.ref}")
    skills_ok = skills_refused = 0
    for directory, parsed in (found for p in paths if p.is_dir() for found in skills_below(p)):
        if isinstance(parsed, InvalidSkill):
            skills_refused += 1
            typer.echo(f"refused    {directory}")
            for finding in parsed.findings:
                typer.echo(f"  - {finding}")
        else:
            skills_ok += 1
            typer.echo(f"ok         {directory}  skill {parsed.name}")
    if skills_ok or skills_refused:
        typer.echo(f"{skills_ok + skills_refused} skill(s): {skills_refused} refused")
    total = checked + unreadable
    typer.echo(
        f"{total} bundle(s): {checked - refused} would register, {refused} refused, "
        f"{unreadable} unreadable; {skipped} file(s) skipped as no process"
    )
    typer.echo(NOT_CHECKED)
    if unreadable or total == 0:
        raise typer.Exit(code=2)
    if refused or skills_refused:
        raise typer.Exit(code=1)


def _bundles(paths: Iterable[Path]) -> Iterable[tuple[Path, bool]]:
    """Each file named, and each YAML file below each directory named, in a stable order; with
    whether it was named itself."""
    for path in paths:
        if path.is_dir():
            found = (p for p in path.rglob("*") if p.suffix in SUFFIXES and p.is_file())
            for file in sorted(found):
                yield file, False
        else:
            yield path, True


def _load(path: Path, *, named: bool) -> dict[str, Any] | None:
    """The bundle's document; None for a file found below a directory whose top-level `kind`
    says it is no process and that lists no steps — a blueprint. A file named is checked
    whatever it says."""
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("the bundle is not a mapping")
    if not named and "kind" in document and "steps" not in document:
        return None
    return document


def skill_on_disk(directory: Path) -> SkillFile:
    """The skill a directory holds: its `SKILL.md` and every other file below it, parsed by
    the catalogue's rule. InvalidSkill where it does not hold to the open format."""
    path = directory / rules.FILE
    if not path.is_file():
        raise InvalidSkill((f"{directory} holds no {rules.FILE}",))
    files = {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }
    front_text, body = rules.split(files[rules.FILE].decode("utf-8"))
    try:
        front = yaml.safe_load(front_text)
    except yaml.YAMLError as error:
        raise InvalidSkill((f"{rules.FILE}: the front matter is not YAML: {error}",)) from error
    return rules.parse(directory.name, front, body, files)


def skills_below(root: Path) -> list[tuple[Path, SkillFile | InvalidSkill]]:
    """Every skill directory under a `skills/` directory below `root`, parsed or with why
    not."""
    found: list[tuple[Path, SkillFile | InvalidSkill]] = []
    for marker in sorted(root.rglob(rules.FILE)):
        directory = marker.parent
        if directory.parent.name != "skills":
            continue
        try:
            found.append((directory, skill_on_disk(directory)))
        except InvalidSkill as error:
            found.append((directory, error))
    return found
