"""`taktusctl guides`: the guides beyond the repository (UC-13.6, ADR-0065).

`check` renders every page of both guides from a checkout at one commit and writes nothing: a
page whose file or section is gone, or that would carry an address or a key, is named with the
reason. `publish --to DIR` puts the guides into a directory of Markdown files, the knowledge
system of an organisation that has no wiki, by the same rules as any knowledge system: a page
a person edited there is kept, and its difference from the repository is printed.

Every file is read from the commit, never from the working tree, so that what a page names as
its commit is what it says.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from taktus.adapters.driving.cli.run_command import DEFAULT_TENANT
from taktus.adapters.driving.cli.wiring import NotOperable, Wiring
from taktus.components.knowledge.application.service import Publication, PublishGuides
from taktus.components.knowledge.domain.model import Manifest, Page, Source
from taktus.components.knowledge.domain.service.render import RenderRefused, digest, render

MANIFEST = "docs/guides/guides.yaml"
"""Where the repository declares its guides."""

EXIT_WITHHELD = 1
EXIT_REFUSED = 2

guides = typer.Typer(
    help="The administration guide and the guide for users, generated from the repository.",
    no_args_is_help=True,
)

Repository = Annotated[
    Path, typer.Option("--repository", help="A checkout of the Taktus repository.")
]
Commit = Annotated[
    str, typer.Option("--commit", help="The commit the guides are rendered at: a ref or a hash.")
]
Places = Annotated[
    list[str] | None,
    typer.Option(
        "--place",
        help="Where a guide goes, as GUIDE=LEVEL/LEVEL (repeat for each guide). Default: the "
        "place the manifest names.",
    ),
]


class Checkout:
    """A checkout read at one commit through git: the reader rendering needs."""

    def __init__(self, root: Path, ref: str) -> None:
        self._root = root
        found = self._git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if found is None:
            raise RenderRefused(f"{ref!r} is no commit of the checkout at {root}")
        self.commit = found.strip()

    def read(self, path: str) -> str | None:
        return self._git("show", f"{self.commit}:{path}")

    def _git(self, *args: str) -> str | None:
        done = subprocess.run(  # noqa: S603 — a fixed program, arguments never through a shell
            ["git", "-C", str(self._root), *args],  # noqa: S607 — git on the path, as make does
            capture_output=True,
            check=False,
        )
        if done.returncode != 0:
            return None
        return done.stdout.decode("utf-8")


def rendered(
    repository: Path, ref: str, places: list[str] | None
) -> tuple[Manifest, Source, tuple[Page, ...]]:
    checkout = Checkout(Path(os.path.expanduser(repository)), ref)
    text = checkout.read(MANIFEST)
    if text is None:
        raise RenderRefused(f"{MANIFEST} does not exist at {checkout.commit}")
    try:
        manifest = Manifest.model_validate(yaml.safe_load(text))
    except (yaml.YAMLError, ValidationError) as error:
        raise RenderRefused(f"{MANIFEST}: {error}") from error
    source = Source(file=MANIFEST, digest=digest(text))
    pages = render(manifest, checkout.read, checkout.commit, _places(places))
    return manifest, source, pages


@guides.command("check")
def check(repository: Repository = Path("."), commit: Commit = "HEAD") -> None:
    """Render every page from the repository and write nothing.

    Exit code 0: every page renders. Exit code 2: a page cannot be rendered; the reason is named.
    """
    try:
        _, _, pages = rendered(repository, commit, None)
    except RenderRefused as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    for page in pages:
        typer.echo(f"{page.guide}/{page.id}  {'/'.join(page.place)}  {page.digest[:19]}")
    typer.echo(f"{len(pages)} pages at {pages[0].commit}")


@guides.command("publish")
def publish(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option(
            "--to",
            help="The directory the guides go into, one Markdown file per page: the knowledge "
            "system of an organisation that has none.",
        ),
    ],
    repository: Repository = Path("."),
    commit: Commit = "HEAD",
    place: Places = None,
    tenant: Annotated[
        str, typer.Option("--tenant", envvar="TAKTUS_TENANT", help="The tenant publishing.")
    ] = DEFAULT_TENANT,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON document.")] = False,
) -> None:
    """Render the guides and put them into a directory; never overwrite a page edited there.

    Exit code 0: every page is the repository's. Exit code 1: a page was edited by hand and
    kept; its difference is printed. Exit code 2: the guides cannot be rendered or published.
    """
    wiring: Wiring = ctx.obj
    try:
        manifest, source, pages = rendered(repository, commit, place)
        directory = Path(os.path.expanduser(to))
        publication = asyncio.run(_publish(wiring, directory, tenant, manifest, source, pages))
    except (RenderRefused, NotOperable) as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    if as_json:
        typer.echo(json.dumps(publication.model_dump(mode="json"), indent=1, ensure_ascii=False))
    else:
        typer.echo(shown(publication))
    raise typer.Exit(code=EXIT_WITHHELD if publication.withheld else 0)


async def _publish(
    wiring: Wiring,
    directory: Path,
    tenant: str,
    manifest: Manifest,
    source: Source,
    pages: tuple[Page, ...],
) -> Publication:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    async with wiring.guides(directory=directory) as services:
        return await services.publish.execute(
            PublishGuides(
                tenant=tenant,
                identity="taktusctl",
                run_id=f"guides-{pages[0].commit[:12]}-{stamp}",
                manifest=manifest,
                manifest_source=source,
                pages=pages,
            )
        )


def shown(publication: Publication) -> str:
    lines = [f"guides at {publication.commit}"]
    for page in publication.pages:
        lines.append(f"  {page.action:<8} {page.state:<9} {'/'.join(page.place)}")
    for page in publication.withheld:
        lines += ["", f"kept, {page.state}: {'/'.join(page.place)}", (page.difference or "")]
    return "\n".join(lines).rstrip()


def _places(given: list[str] | None) -> dict[str, tuple[str, ...]]:
    places: dict[str, tuple[str, ...]] = {}
    for entry in given or ():
        guide, _, levels = entry.partition("=")
        names = tuple(name for name in levels.split("/") if name)
        if not guide or not names:
            raise RenderRefused(f"--place {entry!r} is not GUIDE=LEVEL/LEVEL")
        places[guide] = names
    return places
