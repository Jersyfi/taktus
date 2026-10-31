"""`taktusctl bpmn`: a BPMN model read into plan drafts, a filled draft turned into a bundle, and
a bundle written as BPMN, without an instance (UC-4.23, ADR-0168).

- `bpmn draft MODEL` prints one draft per process of the model, as YAML. A draft is never a
  process: no step has a method chosen, and its `questions` say what is to be answered.
- `bpmn complete DRAFT` turns a draft the person filled in into a bundle, held to the checks of
  `taktusctl bundle check`. Every question still open is named, and nothing is printed then.
- `bpmn export BUNDLE` writes the bundle's version as BPMN, a projection of it.

Nothing is stored and nothing is recorded; no database, login or network is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml

from taktus.components.process.application.service import drafts
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess

bpmn = typer.Typer(
    help="BPMN models in as plan drafts, processes out as BPMN.",
    no_args_is_help=True,
    add_completion=False,
)


@bpmn.command("draft")
def draft(
    model: Annotated[Path, typer.Argument(help="A BPMN 2.0 model, an XML file.", exists=True)],
) -> None:
    """Read a BPMN model into plan drafts, one per process, printed as YAML.

    Exit code 0: the drafts are printed. Exit code 2: the model cannot be read or is refused.
    """
    try:
        found = drafts.read_drafts(model.read_bytes())
    except (OSError, drafts.Unreadable) as error:
        typer.echo(f"unreadable {model}: {error}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(
        yaml.safe_dump_all(
            [d.document() for d in found], sort_keys=False, allow_unicode=True, width=100
        ),
        nl=False,
    )


@bpmn.command("complete")
def complete(
    path: Annotated[Path, typer.Argument(help="A filled plan draft, a YAML file.", exists=True)],
    version: Annotated[str, typer.Option(help="The version the bundle names.")] = "1",
) -> None:
    """Turn a filled plan draft into a bundle, printed as YAML.

    Exit code 0: the bundle would register. Exit code 1: a question is open, or registration
    would refuse it; the findings say which. Exit code 2: the file cannot be read.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        typer.echo(f"unreadable {path}: {error}", err=True)
        raise typer.Exit(code=2) from None
    if not isinstance(document, dict):
        typer.echo(f"unreadable {path}: a draft is a mapping", err=True)
        raise typer.Exit(code=2)
    try:
        bundle = drafts.complete(document, version)
    except InvalidProcess as error:
        typer.echo(f"not yet a bundle {path}", err=True)
        for finding in error.findings:
            typer.echo(f"  - {finding}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(yaml.safe_dump(bundle, sort_keys=False, allow_unicode=True, width=100), nl=False)


@bpmn.command("export")
def export(
    bundle: Annotated[Path, typer.Argument(help="A process bundle, a YAML file.", exists=True)],
    out: Annotated[
        Path | None, typer.Option(help="The file to write; standard output when absent.")
    ] = None,
) -> None:
    """Write a bundle's version as BPMN.

    Exit code 0: written. Exit code 1: the bundle would not register. Exit code 2: it cannot be
    read.
    """
    try:
        document = yaml.safe_load(bundle.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        typer.echo(f"unreadable {bundle}: {error}", err=True)
        raise typer.Exit(code=2) from None
    try:
        version = parse_bundle(document if isinstance(document, dict) else {})
    except InvalidProcess as error:
        typer.echo(f"refused {bundle}", err=True)
        for finding in error.findings:
            typer.echo(f"  - {finding}", err=True)
        raise typer.Exit(code=1) from None
    written = drafts.export(version)
    if out is None:
        typer.echo(written.decode("utf-8"), nl=False)
    else:
        out.write_bytes(written)
