"""The levels of the live representation, the visual vocabulary, and the web app (ADR-0063).

- `GET /levels/runs/{run_id}` — the run level of UC-6.10: the run and each of its steps, every
  fact with its glyph with motion and without, and its text equivalent. Read with an account
  key; a run the reader may not see is answered exactly as one that does not exist.
- `GET /vocabulary` — the visual vocabulary as a document (ADR-0059), for a legend. It says how
  Taktus draws, nothing about any tenant, and needs no key.
- `/app/` — the web app, the static build of `web/`, served where it was built into the image.

The account key is read from `Authorization: Bearer` and nowhere else, as on the rest of the
surface.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Header
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.domain.model import Reader
from taktus.components.reporting.domain.model.vocabulary import VOCABULARY
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}

WEB_PATH = "/app"
"""Where the web app is served, under the prefix."""


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["levels"])

    @routes.get(
        "/levels/runs/{run_id}",
        summary="The run level: where one run stands",
        description="The run and each of its steps in order: method kind, exactness class, "
        "state, what a waiting step waits on, what each step used and what the run consumed "
        "so far — the run component's own figures. Every element carries its glyph twice, "
        "with motion (`drawn.moving`) and without (`drawn.still`), as the visual vocabulary "
        "gives it, and its text equivalent (`text`). Follow `GET /changes?run=…` and read "
        "this again when a change arrives (ADR-0063).",
        responses={
            200: {"description": "The run level."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            404: {
                "description": "No such run, or one you may not see: the two are answered alike.",
                **PROBLEM,
            },
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def run_level(
        run_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        level = await services.levels.run(reader, run_id)
        if level is None:
            return problem(404, f"no run {run_id!r} you may see")
        return JSONResponse(level.document())

    @routes.get(
        "/vocabulary",
        summary="The visual vocabulary",
        description="How every live representation draws a method kind, an exactness class "
        "and a state, as tokens of form, motion, marks and text; no colour (ADR-0059).",
        responses={200: {"description": "The vocabulary."}},
    )
    async def vocabulary() -> JSONResponse:
        return JSONResponse(VOCABULARY.document())

    return routes


def mount_web(app: FastAPI, base: str, directory: Path) -> None:
    """Serve the web app's static build at `{base}/app/`. `{base}/app` is redirected to it
    by a relative location, so that a platform that strips the prefix forwards it too."""

    @app.get(f"{base}{WEB_PATH}", include_in_schema=False)
    async def to_app() -> RedirectResponse:
        return RedirectResponse(url=f"{WEB_PATH.lstrip('/')}/", status_code=308)

    app.mount(f"{base}{WEB_PATH}", StaticFiles(directory=directory, html=True), name="web")
