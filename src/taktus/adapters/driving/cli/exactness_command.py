"""`taktusctl exactness`: the exactness statement of a process bundle (UC-6.9, ADR-0082).

It reads the bundle, holds it to what registration holds it to, and prints the statement that
the version it registers as carries: which checks apply, what they cover, what they do not
cover, and the residual risk. Nothing is stored and nothing is recorded; it needs no wiring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
import yaml

from taktus.components.process.application.service.register_version import statement_of
from taktus.components.process.domain.model import InvalidProcess


def exactness(
    process: Annotated[
        Path, typer.Option("--process", help="The process bundle, a YAML file.", exists=True)
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the statement as data instead of text.")
    ] = False,
) -> None:
    """Print the exactness statement of a process bundle.

    Exit code 0: the statement is printed. Exit code 2: the bundle cannot be read, or it would
    be refused at registration; the findings say why.
    """
    try:
        with process.open(encoding="utf-8") as handle:
            bundle = yaml.safe_load(handle)
        if not isinstance(bundle, dict):
            raise ValueError("the bundle is not a mapping")
    except (OSError, yaml.YAMLError, ValueError) as error:
        typer.echo(f"cannot read {process}: {error}", err=True)
        raise typer.Exit(code=2) from error
    try:
        statement = statement_of(bundle)
    except InvalidProcess as error:
        typer.echo(f"{process} is not a valid process:", err=True)
        for finding in error.findings:
            typer.echo(f"  - {finding}", err=True)
        raise typer.Exit(code=2) from error
    if as_json:
        sys.stdout.write(json.dumps(statement.as_document(), ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(statement.render())
