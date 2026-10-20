"""`taktusctl prices import`: an open model price list becomes a new price table version (#327).

The list is read from a file and written as a file in the shape of `contracts/model/v1`,
`PriceTable`; an operator then points `TAKTUS_PRICE_TABLE` at it, and the next run's budget
statement names its digest. Nothing is fetched, nothing is stored in the instance and an
existing file is never overwritten: a version never changes once used (ADR-0010). It needs no
wiring.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from taktus.components.accounting.domain.service.price_import import import_prices

prices = typer.Typer(help="Price tables.", no_args_is_help=True)


@prices.command("import")
def import_(
    file: Annotated[Path, typer.Argument(help="The price list, a JSON file.", exists=True)],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", help="Where to write the table. Default: price-table-<version>.json."
        ),
    ] = None,
    version: Annotated[
        str | None,
        typer.Option("--version", help="The version name of the table. Default: <today>.1."),
    ] = None,
    currency: Annotated[str, typer.Option("--currency", help="The currency of the list.")] = "usd",
    source: Annotated[
        str | None,
        typer.Option("--source", help="Where the list came from. Default: the file's name."),
    ] = None,
) -> None:
    """Write a new price table version from a price list in LiteLLM's shape, and list what could
    not be mapped.

    Exit code 0: the table is written. Exit code 1: the table is written and some entries could
    not be mapped. Exit code 2: the list cannot be read or maps to nothing, or the file exists.
    """
    now = datetime.now(UTC).replace(microsecond=0)
    name = version or f"{now:%Y-%m-%d}.1"
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
        imported = import_prices(
            document,
            version=name,
            valid_from=now,
            currency=currency,
            source=source or f"imported from {file.name} on {now:%Y-%m-%d}",
        )
    except (OSError, ValueError) as error:
        typer.echo(f"cannot import {file}: {error}", err=True)
        raise typer.Exit(code=2) from error
    target = output or Path(f"price-table-{name}.json")
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(imported.table.model_dump(mode="json", exclude_none=True), indent=2)
            )
            handle.write("\n")
    except OSError as error:
        typer.echo(f"cannot write {target}: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(f"wrote    {target}: version {name}, {len(imported.table.prices)} model(s)")
    for entry in imported.unmapped:
        typer.echo(f"unmapped {entry}")
    raise typer.Exit(code=1 if imported.unmapped else 0)
