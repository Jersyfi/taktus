"""`taktusctl domain`: a tenant's domains with their owners, duties and legal anchors (ADR-0259,
ADR-0280, UC-15.5), and the domain blueprints a domain is instantiated from (ADR-0263, UC-15.1).

`create ID --name N --owner IDENTITY --jurisdiction DE --process P` instantiates a domain; one
without an owner the tenant knows, or under which no legal anchor would be in force, is refused.
`owner ID IDENTITY` names a new owner, `vacate ID` records that the owner left. `list` prints
every domain with its owner, its legal anchors in force and whether its takeover and removal
tests passed. `duties --owner IDENTITY` prints the escalations, raise proposals and takeover
tests of the domains that person owns, each addressed to them. `evidence` generates the
conformity evidence that names the catalogue in force per domain, and prints it. These
authenticate by holding the instance's state, as `budget` does; `--by` names who acts.

A blueprint is named by its directory, the one that holds `blueprint.yaml`. `check` admits each
directory named or refuses it with every finding. `export` copies an admitted blueprint's files
into a directory, as plain files. `start` begins an instance and the plan draft it is worked
out in (ADR-0289), and prints both: the draft's missing parts are the instance's open questions.
Every answer is a revision of the draft: `answer` names the tool that serves a capability
(`none` where the organisation has none), `leave-out` drops processes,
`owner INSTANCE IDENTITY --blueprint DIR` names the domain's one owner, `jurisdiction` the
country whose law its binding acts fall under, `due` the date the plan is due. `propose`
commissions the plan: refused while a part is missing, it instantiates the governance domain
with its owner — the one record `create` makes, through the same service — and makes each kept
process a proposal at level 2 or below; a person commissions each. `offer` takes a later version
of the blueprint and makes a proposal of each changed bundle: nothing is applied. `show` prints
an instance, its plan and its runs counted per process, as JSON.

Every act names who acts with `--identity`, an identity the tenant knows.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from taktus.adapters.driving.cli.incident_command import By, StateDir, Tenant
from taktus.adapters.driving.cli.run_command import (
    DEFAULT_STATE_DIR,
    DEFAULT_TENANT,
    DEFAULT_WORKER,
    resolve_identity,
)
from taktus.adapters.driving.cli.wiring import (
    DomainActs,
    DomainDialogueActs,
    NotOperable,
    Services,
    Wiring,
)
from taktus.components.catalog.application.service import DomainRefused
from taktus.components.catalog.domain.model import DomainInstance
from taktus.components.command.application.service import PlanningError
from taktus.components.command.domain.model import PlanDraft
from taktus.components.governance.application.service.domains import (
    DomainRefused as TenantDomainRefused,
)
from taktus.components.governance.application.service.domains import (
    InstantiateDomain,
    TenantDomains,
    UnknownDomain,
)

EXIT_REFUSED = 1
EXIT_NOT_RUN = 2
NONE = "none"

domain = typer.Typer(
    help="A tenant's domains, each with one owner, its duties and its legal anchors; and the "
    "domain blueprints they are instantiated from: admitted, instantiated in dialogue, exported.",
    no_args_is_help=True,
)

Blueprint = Annotated[
    Path, typer.Option("--blueprint", help="The blueprint's directory, holding blueprint.yaml.")
]
Identity = Annotated[
    str | None,
    typer.Option(
        "--identity", envvar="TAKTUS_IDENTITY", help="Who acts: an identity the tenant knows."
    ),
]


def _run[T](
    ctx: typer.Context,
    state_dir: Path,
    act: Callable[[Services, DomainActs], Awaitable[T]],
) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.domains is None:
                raise NotOperable("domain blueprints cannot be read with these services")
            return await act(services, services.domains)

    try:
        return asyncio.run(opened())
    except DomainRefused as error:
        typer.echo(f"refused ({error.kind}): {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    except PlanningError as error:
        typer.echo(f"refused (plan): {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    except (NotOperable, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_RUN) from error


def _shown(
    domains: DomainActs, instance: DomainInstance, blueprint: Path, draft: PlanDraft | None = None
) -> dict[str, Any]:
    admitted = domains.admitted(blueprint)
    document = instance.document()
    document["questions"] = [q.document() for q in domains.instances.questions(admitted, instance)]
    if draft is not None:
        document["plan"] = {
            "draft": draft.id,
            "version": draft.version,
            "missing": list(draft.missing()),
            "commissioned": draft.is_commissioned,
        }
    return document


def _dialogue(domains: DomainActs) -> DomainDialogueActs:
    if domains.dialogue is None:
        raise NotOperable("a domain is worked out in a plan, which these services do not wire")
    return domains.dialogue


def _echo(document: Any) -> None:
    typer.echo(json.dumps(document, indent=2, ensure_ascii=False, default=str))


@domain.command("check")
def check(
    ctx: typer.Context,
    directories: Annotated[list[Path], typer.Argument(help="Blueprint directories.")],
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Admit each blueprint, or refuse it with every finding. Exit code 1: one is refused."""

    async def act(_: Services, domains: DomainActs) -> list[Any]:
        return [domains.read(d) for d in directories]

    refused = False
    for read in _run(ctx, state_dir, act):
        if read.admitted is not None:
            blueprint = read.admitted.blueprint
            typer.echo(
                f"admitted   {read.directory}  {blueprint.id} {blueprint.version}: "
                f"{len(blueprint.processes)} processes, {len(read.admitted.bundles)} with a bundle"
            )
            continue
        refused = True
        typer.echo(f"refused    {read.directory}")
        for finding in read.admission.findings:
            typer.echo(f"  {finding}")
    if refused:
        raise typer.Exit(code=EXIT_REFUSED)


@domain.command("export")
def export(
    ctx: typer.Context,
    directory: Annotated[Path, typer.Argument(help="The blueprint's directory.")],
    target: Annotated[Path, typer.Argument(help="Where its files are copied to.")],
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Copy an admitted blueprint and the bundles it names, as plain files."""

    async def act(_: Services, domains: DomainActs) -> list[Path]:
        return domains.export(directory, target)

    for path in _run(ctx, state_dir, act):
        typer.echo(str(path))


@domain.command("start")
def start(
    ctx: typer.Context,
    blueprint: Blueprint,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Begin an instance of the blueprint and print it with its questions, as JSON."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        instance, draft = await _dialogue(domains).start(
            tenant, domains.admitted(blueprint), placed.identity, placed.org_path
        )
        return _shown(domains, instance, blueprint, draft)

    _echo(_run(ctx, state_dir, act))


@domain.command("answer")
def answer(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    capability: Annotated[str, typer.Argument(help="The capability asked for.")],
    adapter: Annotated[str, typer.Argument(help="The adapter that serves it, or `none`.")],
    blueprint: Blueprint,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Answer which tool serves a capability."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        changed, draft = await _dialogue(domains).answer(
            tenant,
            domains.admitted(blueprint),
            instance,
            capability,
            None if adapter == NONE else adapter,
            placed.identity,
        )
        return _shown(domains, changed, blueprint, draft)

    _echo(_run(ctx, state_dir, act))


@domain.command("leave-out")
def leave_out(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    processes: Annotated[list[str], typer.Argument(help="The blueprint's processes to drop.")],
    blueprint: Blueprint,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Drop processes the organisation does not need."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        changed, draft = await _dialogue(domains).leave_out(
            tenant, domains.admitted(blueprint), instance, processes, placed.identity
        )
        return _shown(domains, changed, blueprint, draft)

    _echo(_run(ctx, state_dir, act))


@domain.command("owner")
def owner(
    ctx: typer.Context,
    target: Annotated[
        str, typer.Argument(help="The domain, or with --blueprint the blueprint's instance.")
    ],
    person: Annotated[str, typer.Argument(help="Its one owner from now on: an identity.")],
    blueprint: Annotated[
        Path | None,
        typer.Option(
            "--blueprint",
            help="The blueprint's directory: TARGET is an instance of it, not a domain.",
        ),
    ] = None,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Name a domain's owner from now on, or, with --blueprint, an instance's one owner: a
    revision of its plan draft (ADR-0289)."""
    if blueprint is not None:
        named = blueprint

        async def instance_owner(services: Services, domains: DomainActs) -> dict[str, Any]:
            placed = await resolve_identity(services, identity, tenant)
            changed, draft = await _dialogue(domains).name_owner(
                tenant, domains.admitted(named), target, person, placed.identity
            )
            return _shown(domains, changed, named, draft)

        _echo(_run(ctx, state_dir, instance_owner))
        return

    async def domain_owner(services: Services) -> dict[str, Any]:
        domains = _tenant_domains(services)
        return (await domains.name_owner(tenant, target, person, by=by)).document()

    _echo(_governed(ctx, state_dir, domain_owner))


@domain.command("jurisdiction")
def jurisdiction(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    code: Annotated[str, typer.Argument(help="An ISO 3166 code, as DE or DE-BY.")],
    blueprint: Blueprint,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Name the country or region whose law the domain's binding acts fall under."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        changed, draft = await _dialogue(domains).name_jurisdiction(
            tenant, domains.admitted(blueprint), instance, code, placed.identity
        )
        return _shown(domains, changed, blueprint, draft)

    _echo(_run(ctx, state_dir, act))


@domain.command("due")
def due(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    date: Annotated[str, typer.Argument(help="The date the plan is due, as 2026-12-01.")],
    blueprint: Blueprint,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Name the date the instance's plan is due."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        when = datetime.fromisoformat(date)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        draft = await _dialogue(domains).due(tenant, instance, when, placed.identity)
        found = await domains.instances.get(tenant, instance)
        return _shown(domains, found, blueprint, draft)

    _echo(_run(ctx, state_dir, act))


@domain.command("propose")
def propose(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    blueprint: Blueprint,
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Commission the instance's plan: refused while a part is missing, a question among
    them. It instantiates the governance domain with its owner, and makes each kept process a
    proposal at level 2 or below. A person commissions each proposal; nothing is registered
    here."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        dialogue = _dialogue(domains)
        changed, _ = await dialogue.commission(
            tenant, domains.admitted(blueprint), instance, placed.identity
        )
        return _shown(domains, changed, blueprint, await dialogue.draft(tenant, changed))

    _echo(_run(ctx, state_dir, act))


@domain.command("offer")
def offer(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    blueprint: Annotated[Path, typer.Option("--blueprint", help="The later version's directory.")],
    identity: Identity = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Offer a later version of the blueprint: each changed bundle becomes a proposal."""

    async def act(services: Services, domains: DomainActs) -> dict[str, Any]:
        placed = await resolve_identity(services, identity, tenant)
        made = await domains.instances.offer(
            tenant, domains.admitted(blueprint), instance, by=placed.identity
        )
        return made.document()

    _echo(_run(ctx, state_dir, act))


@domain.command("show")
def show(
    ctx: typer.Context,
    instance: Annotated[str, typer.Argument(help="The instance.")],
    blueprint: Blueprint,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """The instance, its open questions and its runs counted per process, as JSON."""

    async def act(_: Services, domains: DomainActs) -> dict[str, Any]:
        found = await domains.instances.get(tenant, instance)
        draft = (
            None
            if found.plan is None or domains.dialogue is None
            else await domains.dialogue.draft(tenant, found)
        )
        document = _shown(domains, found, blueprint, draft)
        document["figures"] = (await domains.figures(tenant, found)).document()
        return document

    _echo(_run(ctx, state_dir, act))


# --- a tenant's domains (ADR-0259, ADR-0280) ---------------------------------------------------


def _governed[T](ctx: typer.Context, state_dir: Path, act: Callable[[Services], Awaitable[T]]) -> T:
    wiring: Wiring = ctx.obj
    where = Path(os.path.expanduser(state_dir))

    async def opened() -> T:
        async with wiring.services(state_dir=where, worker_endpoint=DEFAULT_WORKER) as services:
            if services.tenant_domains is None:
                raise NotOperable("the tenant's domains cannot be read with these services")
            return await act(services)

    try:
        return asyncio.run(opened())
    except (NotOperable, TenantDomainRefused, UnknownDomain, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error


def _tenant_domains(services: Services) -> TenantDomains:
    if services.tenant_domains is None:
        raise NotOperable("the tenant's domains cannot be read with these services")
    return services.tenant_domains


@domain.command("create")
def create(
    ctx: typer.Context,
    domain_id: Annotated[str, typer.Argument(help="The domain's identifier: finance.")],
    name: Annotated[str, typer.Option("--name", help="Its name as people say it.")],
    owner: Annotated[str, typer.Option("--owner", help="The identity that owns it.")],
    jurisdiction: Annotated[
        str, typer.Option("--jurisdiction", help="ISO 3166, a country or region: DE, DE-BY.")
    ],
    process: Annotated[
        list[str] | None, typer.Option("--process", help="A process of it. Repeatable.")
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Instantiate a domain with its owner, and print it, as JSON."""

    async def act(services: Services) -> dict[str, Any]:
        domains = _tenant_domains(services)
        made = await domains.instantiate(
            InstantiateDomain(
                tenant=tenant,
                domain=domain_id,
                name=name,
                owner=owner,
                jurisdiction=jurisdiction,
                processes=tuple(process or ()),
            ),
            by=by,
        )
        return made.document()

    _echo(_governed(ctx, state_dir, act))


@domain.command("vacate")
def vacate(
    ctx: typer.Context,
    domain_id: Annotated[str, typer.Argument(help="The domain whose owner left.")],
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Record that the owner left: the domain is shown without one until one is named."""

    async def act(services: Services) -> dict[str, Any]:
        domains = _tenant_domains(services)
        return (await domains.vacate(tenant, domain_id, by=by)).document()

    _echo(_governed(ctx, state_dir, act))


@domain.command("list")
def list_(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print every domain with its owner, its legal anchors in force and its tests, as JSON."""

    async def act(services: Services) -> list[dict[str, Any]]:
        domains = _tenant_domains(services)
        return [
            {**v.document(), "runs_without_taktus": v.runs_without_taktus}
            for v in await domains.views(tenant)
        ]

    _echo(_governed(ctx, state_dir, act))


@domain.command("duties")
def duties(
    ctx: typer.Context,
    owner: Annotated[
        str | None, typer.Option("--owner", help="Only the domains this identity owns.")
    ] = None,
    tenant: Tenant = DEFAULT_TENANT,
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Print each domain's escalations, raise proposals and takeover tests, addressed to its
    owner, as JSON."""

    async def act(services: Services) -> list[dict[str, Any]]:
        domains = _tenant_domains(services)
        return [d.document() for d in await domains.duties(tenant, owner=owner)]

    _echo(_governed(ctx, state_dir, act))


@domain.command("evidence")
def evidence(
    ctx: typer.Context,
    tenant: Tenant = DEFAULT_TENANT,
    by: By = "operator",
    state_dir: StateDir = Path(DEFAULT_STATE_DIR),
) -> None:
    """Generate the conformity evidence of the tenant's domains, and print it, as JSON."""

    async def act(services: Services) -> dict[str, Any]:
        if services.conformity is None:
            raise NotOperable("conformity evidence cannot be generated with these services")
        return await services.conformity.generate(tenant, by=by)

    _echo(_governed(ctx, state_dir, act))
