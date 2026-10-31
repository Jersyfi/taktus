"""`taktusctl catalogue`: the catalogue of signed adapters and bundles (ADR-0175, UC-14.6).

`list` prints every entry of every index in `TAKTUS_CATALOGUE_DIRECTORY`, whether the instance
admits it against `TAKTUS_CATALOGUE_KEYS` and why not, and, for an installed entry, its tier
here and what keeps it from *verified*. `install` verifies one entry and installs it: an image
as the adapter identifier `--as` names, printing the image by digest for the deployment to
pull; a bundle as a proposal a person decides on. The person who installs it is the actor in
the ledger and must be an identity the tenant knows.

`key` and `sign` are the author's: they read a seed of thirty-two bytes from a file and never
print it. `key` prints the public key an operator lists as trusted; `sign` fills each bundle's
digest from its file and signs every entry of an index in place.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.catalog.application.service import NotAdmitted
from taktus.components.process.domain.model import InvalidProcess

EXIT_REFUSED = 1
EXIT_NOT_RUN = 2
SEED_BYTES = 32

catalogue = typer.Typer(
    help="The catalogue: signed adapters and bundles, verified and installed.",
    no_args_is_help=True,
)

Seed = Annotated[
    Path,
    typer.Option(
        "--seed-file",
        help="A file holding the author's seed of 32 bytes. It is read and never printed.",
    ),
]


def _seed(path: Path) -> bytes:
    try:
        seed = Path(os.path.expanduser(path)).read_bytes()
    except OSError as error:
        typer.echo(f"error: the seed cannot be read: {error.strerror}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    if len(seed) < SEED_BYTES:
        typer.echo(f"error: a seed is {SEED_BYTES} bytes; the file holds fewer", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN)
    return seed[:SEED_BYTES]


@catalogue.command("list")
def listed(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Every entry of every index, admitted or refused, and its tier here once installed."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def act() -> tuple[list[Any], list[Any]]:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.catalogue_index is None:
                raise NotOperable("this instance reads no catalogue")
            return await services.catalogue_index.listed(tenant)

    try:
        rows, refused = asyncio.run(act())
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    if not rows and not refused:
        typer.echo("the catalogue is empty")
    for row in rows:
        entry = row.entry
        verdict = "admitted" if row.admitted else "refused"
        typer.echo(
            f"{row.catalogue}/{entry.id} {entry.version}  {entry.kind}  {entry.tier}  {verdict}"
        )
        typer.echo(f"  {entry.summary}")
        if entry.kind == "image":
            typer.echo(f"  {entry.family} for {entry.contract}: {', '.join(entry.capabilities)}")
        for finding in row.findings:
            typer.echo(f"  refused: {finding}")
        if row.installed_as is not None:
            typer.echo(f"  installed as {row.installed_as}, {row.standing} here")
        for gap in row.missing:
            typer.echo(f"  missing: {gap}")
    for read in refused:
        typer.echo(f"{read.path.name}  refused: {read.refused}")


@catalogue.command("install")
def install(
    ctx: typer.Context,
    entry: Annotated[str, typer.Argument(help="The entry, as <catalogue>/<id>.")],
    adapter: Annotated[
        str | None,
        typer.Option(
            "--as",
            help="For an image: the adapter identifier it is installed as, of its family: "
            "worker.<name>, connector.<label>, model.<name>.",
        ),
    ] = None,
    identity: Annotated[
        str | None,
        typer.Option(
            "--identity",
            envvar="TAKTUS_IDENTITY",
            help="Who installs it: an identity the tenant knows. The ledger names it.",
        ),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Verify one entry and install it; record its origin in the ledger.

    Exit code 0: installed. Exit code 1: refused, with every reason; nothing is recorded.
    Exit code 2: nothing ran.
    """
    catalogue_name, _, entry_id = entry.partition("/")
    if not entry_id:
        typer.echo("error: name the entry as <catalogue>/<id>", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN)
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def act() -> Any:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.catalogue_index is None:
                raise NotOperable("this instance reads no catalogue")
            placed = await resolve_identity(services, identity, tenant)
            return await services.catalogue_index.install(
                tenant, catalogue_name, entry_id, actor=placed.identity, adapter=adapter
            )

    try:
        installed = asyncio.run(act())
    except NotAdmitted as error:
        typer.echo(f"refused: {entry}", err=True)
        for finding in error.findings:
            typer.echo(f"  {finding}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    except InvalidProcess as error:
        typer.echo(f"refused: {entry}", err=True)
        for finding in error.findings:
            typer.echo(f"  {finding}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    record = installed.installation
    typer.echo(f"installed {entry} as {record.id}, {record.tier}, signed by {record.author}")
    if installed.pull is not None:
        typer.echo(f"  pull by digest: {installed.pull}")
    if record.proposal is not None:
        typer.echo(f"  proposal {record.proposal} for {record.process_version}: a person decides")
    typer.echo(
        f"  ledger: {installed.entry.kind} seq {installed.entry.seq}, "
        f"evidence {installed.entry.content_digest}"
    )


@catalogue.command("key")
def key(ctx: typer.Context, seed: Seed) -> None:
    """Print the public key of the seed: what an operator lists as trusted."""
    wiring: Wiring = ctx.obj
    typer.echo(wiring.catalogue_author().key(_seed(seed)))


@catalogue.command("sign")
def sign(
    ctx: typer.Context,
    index: Annotated[Path, typer.Argument(help="The index file to sign in place.")],
    seed: Seed,
) -> None:
    """Fill each bundle's digest from its file and sign every entry of the index."""
    wiring: Wiring = ctx.obj
    try:
        signed = wiring.catalogue_author().sign(Path(os.path.expanduser(index)), _seed(seed))
    except (OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    for entry_id in signed:
        typer.echo(f"signed {entry_id}")
