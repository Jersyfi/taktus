"""`taktusctl identity`: the administrator's acts on identities and links (ADR-0040).

`add` adds an identity and prints its first account key, once: the person proves their Taktus
account with it on the control plane's surface. `key` issues a new key, and the old one stops
working. `links` lists every link of the tenant — active and revoked — and `revoke` revokes
one: the next event from that account is from an unknown sender. Every act is a ledger entry.

The command line authenticates by holding the instance's state: whoever can run it against the
database is its administrator. `--identity` names the administrator who acts, for the ledger.
Linking an account is not here: only the person, with a link code from their account, or the
organisation's identity source makes a link.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

import typer

from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
)
from taktus.adapters.driving.cli.wiring import NotOperable, Services, Wiring
from taktus.components.identity.application.service import IdentityError, IdentityExists

identity = typer.Typer(help="Identities and the links of channel accounts.", no_args_is_help=True)

StateDir = Annotated[
    Path,
    typer.Option("--state-dir", envvar="TAKTUS_STATE_DIR", help="Where the state is written."),
]
Tenant = Annotated[
    str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant to act in.")
]
By = Annotated[
    str | None,
    typer.Option("--identity", envvar="TAKTUS_IDENTITY", help="The administrator who acts."),
]


def _with[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            return await act(services)

    try:
        return asyncio.run(opened())
    except (IdentityError, NotOperable) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


@identity.command("add")
def add(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The identity's identifier, e.g. idn_ada.")],
    org_path: Annotated[
        str | None,
        typer.Option(
            "--org-path",
            help="Where the identity sits, slash-separated, starting at the tenant: "
            "default/finance/payables. Default: the tenant.",
        ),
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Add an identity and print its account key, once.

    An identity that exists with the same path is left as it is: exit code 0, no key. One
    with another path is refused: exit code 2.
    """
    path = tuple(p for p in (org_path or tenant).split("/") if p)

    async def act(services: Services) -> str | None:
        try:
            _, key = await services.identities.add(tenant, name, path, by=by)
        except IdentityExists as exists:
            if exists.identity.org_path != path:
                raise
            return None
        return key

    key = _with(ctx, state_dir, act)
    if key is None:
        typer.echo(f"identity {name} exists in {tenant}, under {'/'.join(path)}; unchanged")
        return
    typer.echo(f"identity {name} added in {tenant}, under {'/'.join(path)}")
    typer.echo(f"account key, shown once — hand it to the person: {key}")


@identity.command("key")
def key(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The identity that gets a new key.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Issue a new account key for an identity; the old one stops working."""

    async def act(services: Services) -> str:
        return await services.identities.issue_key(tenant, name, by=by)

    issued = _with(ctx, state_dir, act)
    typer.echo(f"account key of {name}, shown once — hand it to the person: {issued}")


@identity.command("links")
def links(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """List every link of the tenant: active and revoked, oldest first."""

    async def act(services: Services) -> list[str]:
        lines = []
        for link in await services.identities.links(tenant):
            state = "active" if link.active else f"revoked {link.revoked_at:%Y-%m-%d %H:%M}"
            lines.append(
                f"{link.id}  {link.channel}  {link.account}  →  {link.identity}  "
                f"({link.origin}, {link.linked_at:%Y-%m-%d %H:%M}; {state})"
            )
        return lines

    listed = _with(ctx, state_dir, act)
    typer.echo("\n".join(listed) if listed else f"tenant {tenant} has no links")


@identity.command("revoke")
def revoke(
    ctx: typer.Context,
    link: Annotated[str, typer.Argument(help="The link to revoke, as `links` lists it.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = None,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Revoke a link: the next event from that account is from an unknown sender."""

    async def act(services: Services) -> str:
        revoked = await services.identities.revoke(tenant, link, by=by)
        return f"{revoked.id} revoked: {revoked.channel} {revoked.account} is nobody's now"

    typer.echo(_with(ctx, state_dir, act))
