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

`share`, `withdraw`, `shares` and `use` keep the catalogue's entries per circle of the
organisation's structure (ADR-0246); `bind-credential` names the parameter an identity's own
credential is provided under, for a shared connector (ADR-0247).
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
from taktus.components.catalog.application.service import NotAdmitted, ShareEntry
from taktus.components.catalog.domain.model import Origin, ShareError, ShareKind
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


# --- shares (ADR-0246, ADR-0247) -----------------------------------------------------------------

Identity = Annotated[
    str | None,
    typer.Option(
        "--identity",
        envvar="TAKTUS_IDENTITY",
        help="Who acts: an identity the tenant knows. The ledger names it.",
    ),
]
Kind = Annotated[str, typer.Argument(help="model, agent, connector or skill.")]
Subject = Annotated[
    str,
    typer.Argument(
        help="The adapter identifier of a model or a connector, or the agent's or skill's name."
    ),
]


def _kind(given: str) -> ShareKind:
    try:
        return ShareKind(given)
    except ValueError as error:
        typer.echo("error: the kind is model, agent, connector or skill", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error


def _shares(services: Any) -> Any:
    if services.shares is None:
        raise NotOperable("this instance keeps no shares")
    return services.shares


@catalogue.command("share")
def share(
    ctx: typer.Context,
    kind: Kind,
    subject: Subject,
    purpose: Annotated[str, typer.Option("--purpose", help="What the entry is for.")],
    circle: Annotated[
        list[str],
        typer.Option(
            "--circle",
            help="A path of the structure (acme/sales) or identity:<id>; repeat for several.",
        ),
    ],
    owner: Annotated[
        str | None, typer.Option("--owner", help="Who answers for it; the actor by default.")
    ] = None,
    location: Annotated[
        str | None, typer.Option("--location", help="A model: own, eu or elsewhere.")
    ] = None,
    cost_model: Annotated[
        str | None,
        typer.Option("--cost-model", help="A model: per_token, per_window, per_hardware_time."),
    ] = None,
    origin: Annotated[
        str | None, typer.Option("--origin", help="A model: provided or trained.")
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", help="A trained model: its file's digest.")
    ] = None,
    evaluation: Annotated[
        list[str] | None,
        typer.Option("--evaluation", help="A trained model: an evaluation that admitted it."),
    ] = None,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Share an entry with circles, replacing the circles it was shared with.

    Exit code 0: shared. Exit code 1: refused, with the reason. Exit code 2: nothing ran.
    """
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))
    shared_kind = _kind(kind)

    async def act() -> Any:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            placed = await resolve_identity(services, identity, tenant)
            return await _shares(services).share(
                ShareEntry(
                    tenant=tenant,
                    kind=shared_kind,
                    subject=subject,
                    owner=owner or placed.identity,
                    purpose=purpose,
                    circles=tuple(circle),
                    actor=placed.identity,
                    location=location,  # type: ignore[arg-type]
                    cost_model=cost_model,  # type: ignore[arg-type]
                    origin=None if origin is None else Origin(origin),
                    version=version,
                    evaluations=tuple(evaluation or ()),
                )
            )

    try:
        done = asyncio.run(act())
    except ShareError as error:
        typer.echo(f"refused ({error.reason}): {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    typer.echo(f"shared {done.id} with {', '.join(done.circles)}")


@catalogue.command("withdraw")
def withdraw(
    ctx: typer.Context,
    kind: Kind,
    subject: Subject,
    despite_broke: Annotated[
        bool,
        typer.Option(
            "--despite-broke",
            help="Withdraw a model or a connector whose removal test says it breaks a process.",
        ),
    ] = False,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Withdraw a share: a model or a connector only with its removal verdict known."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))
    shared_kind = _kind(kind)

    async def act() -> Any:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            placed = await resolve_identity(services, identity, tenant)
            return await _shares(services).withdraw(
                tenant, shared_kind, subject, placed.identity, despite_broke=despite_broke
            )

    try:
        asyncio.run(act())
    except ShareError as error:
        typer.echo(f"refused ({error.reason}): {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    typer.echo(f"withdrew {shared_kind}:{subject}")


@catalogue.command("shares")
def shares(
    ctx: typer.Context,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Every share the identity is inside, with its owner, purpose and circles."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def act() -> list[Any]:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            placed = await resolve_identity(services, identity, tenant)
            listed: list[Any] = await _shares(services).visible(
                tenant, placed.identity, placed.org_path
            )
            return listed

    try:
        found = asyncio.run(act())
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    if not found:
        typer.echo("nothing is shared with you")
    for entry in found:
        typer.echo(f"{entry.id}  {entry.state}  owner {entry.owner}")
        typer.echo(f"  {entry.purpose}")
        typer.echo(f"  circles: {', '.join(entry.circles)}")
        if entry.kind == "model":
            typer.echo(f"  processes {entry.location}, billed {entry.cost_model}, {entry.origin}")


@catalogue.command("use")
def use(
    ctx: typer.Context,
    kind: Kind,
    subject: Subject,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """An entry's calls per organisational unit, and your own: never another person's."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))
    shared_kind = _kind(kind)

    async def act() -> Any:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            placed = await resolve_identity(services, identity, tenant)
            if services.catalogue_use is None:
                raise NotOperable("this instance counts no use")
            return await services.catalogue_use.of(tenant, shared_kind, subject, placed.identity)

    try:
        seen = asyncio.run(act())
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    typer.echo(f"{shared_kind}:{subject}  {seen.total} calls, {seen.own} of them yours")
    for unit, calls in seen.by_unit.items():
        typer.echo(f"  {unit}  {calls}")


@catalogue.command("bind-credential")
def bind_credential(
    ctx: typer.Context,
    of: Annotated[str, typer.Argument(help="The identity whose own credential it is.")],
    name: Annotated[str, typer.Argument(help="The credential name a step names: TICKETS_TOKEN.")],
    suffix: Annotated[
        str,
        typer.Argument(
            help="The suffix of the parameter its value is provided under: the value is read "
            "from the file TAKTUS_CREDENTIAL_<NAME>_<SUFFIX>_FILE names."
        ),
    ],
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Bind an identity's own credential for a shared connector (ADR-0247). No value is read."""
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def act() -> Any:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            placed = await resolve_identity(services, identity, tenant)
            return await _shares(services).bind_credential(
                tenant, of, name, suffix, placed.identity
            )

    try:
        bound = asyncio.run(act())
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error
    typer.echo(f"{of}'s {name} is read from TAKTUS_CREDENTIAL_{bound.parameter}_FILE")
