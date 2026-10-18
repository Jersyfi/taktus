"""`taktusctl bundle check`: process bundles held to registration's rules, without an instance.

It reads each bundle and holds it to what registration holds it to (`parse_bundle`): the shape,
every step's rules, the graph, and the exactness statement (ADR-0113 §4). It needs no wiring, no
database, no login and no network, so that a repository holding bundles can run it in its own
CI. Nothing is stored and nothing is recorded.

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
    total = checked + unreadable
    typer.echo(
        f"{total} bundle(s): {checked - refused} would register, {refused} refused, "
        f"{unreadable} unreadable; {skipped} file(s) skipped as no process"
    )
    typer.echo(NOT_CHECKED)
    if unreadable or total == 0:
        raise typer.Exit(code=2)
    if refused:
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
