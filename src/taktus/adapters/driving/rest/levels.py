"""The levels of the live representation, the visual vocabulary, and the web app (ADR-0063).

- `GET /levels/runs/{run_id}` — the run level of UC-6.10: the run and each of its steps, every
  fact with its glyph with motion and without, and its text equivalent. Read with an account
  key; a run the reader may not see is answered exactly as one that does not exist.
- `GET /levels/runs/{run_id}/stages` — the stage view of UC-6.15: the run as stages, each done,
  current or ahead, with the role a waiting stage waits for and no step graph. Computed from
  the run level's records.
- `GET /levels/overview` — the overview: the areas the reader may look into, their processes,
  how many runs of each work and wait right now, the steps running now (ADR-0067).
- `GET /levels/processes/{process_id}` — the process level: one version's steps as a graph, each
  with how it works and the runs it is running in, with the autonomy statement and the runs of
  the version (ADR-0064). A process the reader may not see is answered as one that does not exist.
- `GET /levels/origins/{run_id}/{step_id}` — the origin of a result: the path back from a step's
  result through the steps and sources that produced it, from the provenance records (ADR-0068).
- `GET /levels/runs/{run_id}/steps/{step_id}/trace` — the trace inside a worker's step: every
  event the worker reported, masked, each with its sentence, from a position on (ADR-0135). A
  reader asks again with `after` while the step is in flight. `POST …/trace/shares` shares it
  with a role and `DELETE …/trace/shares/{role}` withdraws the share; each answers the trace,
  with the link to it in the web app.
- `GET /vocabulary` — the visual vocabulary as a document (ADR-0059), for a legend. It says how
  Taktus draws, nothing about any tenant, and needs no key.
- `/app/` — the web app, the static build of `web/`, served where it was built into the image.

The account key is read from `Authorization: Bearer` and nowhere else, as on the rest of the
surface; the web app's session cookie is accepted in its place (ADR-0119).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Header, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.application.service import BadRole
from taktus.components.reporting.domain.model import Reader
from taktus.components.reporting.domain.model.vocabulary import VOCABULARY
from taktus.ports.identity import Resolution
from taktus.ports.traces import ROLE_PATTERN

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}


class Share(BaseModel):
    """A field the surface does not know — a person among them — is refused."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(
        pattern=ROLE_PATTERN,
        description="The role the trace is shared with: a lowercase token such as `reviewer`. "
        "Never a person.",
    )


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
        "/levels/runs/{run_id}/stages",
        summary="The stages of a run, for a participant",
        description="The run as stages in words: each is done, current or ahead, and a stage "
        "that waits names the role it waits for, never a person; the owner where the wait "
        "names none. No step, method or exactness class; `link` is the run level. Follow "
        "`GET /changes?run=…` and read this again when a change arrives (UC-6.15).",
        responses={
            200: {"description": "The stages."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            404: {
                "description": "No such run, or one you may not see: the two are answered alike.",
                **PROBLEM,
            },
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def run_stages(
        run_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        view = await services.levels.stages(reader, run_id)
        if view is None:
            return problem(404, f"no run {run_id!r} you may see")
        return JSONResponse(view.document())

    @routes.get(
        "/levels/overview",
        summary="The overview: the areas you may look into, their processes, how busy each is",
        description="Every area you may look into — until the organisation's structure is "
        "recorded, your tenant is the one area — with every process in it you may see: its "
        "name, its active version and autonomy level, how many of its runs work right now "
        "and how many wait (the run component's own definitions, counted over the runs you "
        "may see), and the steps running right now, each with its glyph with motion and "
        "without. Follow `GET /changes` and read this again when a change arrives "
        "(ADR-0067).",
        responses={
            200: {"description": "The overview."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def overview(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        return JSONResponse((await services.levels.overview(reader)).document())

    @routes.get(
        "/levels/processes/{process_id}",
        summary="The process level: a process version as a graph",
        description="The steps of one version of a process — the active one, or the one "
        "`version` names — each with how it works: method kind, exactness class, why that "
        "method, what was not chosen, where it falls back, which steps it follows, and the "
        "runs it is running in right now. With the process's autonomy statement — the level "
        "it runs at and why (ADR-0026) — its registered versions, and the runs of the version "
        "you may see. Every element carries its glyph with motion and without, and its text "
        "equivalent. Follow `GET /changes?process=…` and read this again when a change "
        "arrives (ADR-0064).",
        responses={
            200: {"description": "The process level."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            404: {
                "description": "No such process or version, or one you may not see: answered "
                "alike.",
                **PROBLEM,
            },
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def process_level(
        process_id: str,
        version: str | None = Query(
            default=None, min_length=1, description="The version; the active one when absent."
        ),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        level = await services.levels.process(reader, process_id, version)
        if level is None:
            named = process_id if version is None else f"{process_id}@{version}"
            return problem(404, f"no process {named!r} you may see")
        return JSONResponse(level.document())

    @routes.get(
        "/levels/origins/{run_id}/{step_id}",
        summary="The origin of a result: the path back to what produced it",
        description="The result of one step of one run, and the path back from it: the step "
        "that produced it and every step whose result or artifact it read, across runs, each "
        "with how it works — method kind, exactness class, model and adapter where the record "
        "names them, when it was recorded — and every external source read, with when it was "
        "read. Drawn from the provenance records (ADR-0021) and nothing else; a past result is "
        "drawn as it was recorded, never replayed. Every element carries its glyph with motion "
        "and without, and its text equivalent (ADR-0068).",
        responses={
            200: {"description": "The origin of the result."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            404: {
                "description": "No such run or step, a step that produced no result, or one you "
                "may not see: answered alike.",
                **PROBLEM,
            },
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def origin_level(
        run_id: str, step_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        level = await services.levels.origin(reader, run_id, step_id)
        if level is None:
            return problem(404, f"no result of {run_id}/{step_id} you may see")
        return JSONResponse(level.document())

    trace_responses: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {
            "description": "No such run or worker step, or a trace you may not see: answered "
            "alike.",
            **PROBLEM,
        },
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.get(
        "/levels/runs/{run_id}/steps/{step_id}/trace",
        summary="The trace inside a worker's step",
        description="Every event the step's worker reported, in order, after the position "
        "`after`: its type, what the worker contract carries for it with every secret value "
        "masked, and its sentence (`text`). `open` says whether more may come: read again "
        "with the answer's `after` while it is. Shown to a reader who may see the run and "
        "holds the role `owner` or a role the trace is shared with (`shared_with`); `link` is "
        "where the web app shows it. The ledger holds none of it (ADR-0135).",
        responses={200: {"description": "The trace."}, **trace_responses},
    )
    async def trace(
        run_id: str,
        step_id: str,
        after: int = Query(default=0, ge=0, description="The last position already read."),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        view = await services.traces.read(reader, run_id, step_id, after=after)
        if view is None:
            return problem(404, f"no trace of {run_id}/{step_id} you may see")
        return JSONResponse(view.document())

    @routes.post(
        "/levels/runs/{run_id}/steps/{step_id}/trace/shares",
        summary="Share the trace inside a step with a role",
        description="Every signed-in identity that holds the role and may see the run may "
        "then read the trace, at the answer's `link`. A share names a role, never a person; "
        "it never widens what the role may see of runs. The ledger records it as "
        "`trace.shared`, with the role as outcome and you as actor (ADR-0135).",
        responses={
            200: {"description": "The trace, with the role among `shared_with`."},
            **trace_responses,
        },
    )
    async def share(
        run_id: str,
        step_id: str,
        body: Share,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        try:
            view = await services.traces.share(reader, run_id, step_id, body.role)
        except BadRole as error:
            return problem(422, str(error))
        if view is None:
            return problem(404, f"no trace of {run_id}/{step_id} you may see")
        return JSONResponse(view.document())

    @routes.delete(
        "/levels/runs/{run_id}/steps/{step_id}/trace/shares/{role}",
        summary="Withdraw a share of the trace inside a step",
        description="The role no longer reads the trace by this share. The ledger records it "
        "as `trace.unshared` (ADR-0135).",
        responses={200: {"description": "The trace, without the role."}, **trace_responses},
    )
    async def unshare(
        run_id: str,
        step_id: str,
        role: str,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        try:
            view = await services.traces.unshare(reader, run_id, step_id, role)
        except BadRole as error:
            return problem(422, str(error))
        if view is None:
            return problem(404, f"no trace of {run_id}/{step_id} you may see")
        return JSONResponse(view.document())

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
