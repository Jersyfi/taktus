"""What acts for a tenant, what depends on it, and how a process really runs, on the HTTP
surface (ADR-0147, UC-7.8, UC-6.15, UC-9.7).

Read with an account key in `Authorization: Bearer`, or the web app's session. A process the
reader may not see is left out of every row and every count, and a run the reader may not see
is answered as one that does not exist (ADR-0055 §5). The stop is ADR-0138's, requested by the
person and asking no reason. No row and no figure names a person (principle 14).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.domain.model import Reader
from taktus.components.run.application.service.stops import NotStoppable
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
UNAUTHENTICATED: dict[int | str, dict[str, Any]] = {
    401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
    422: {"description": "A parameter does not validate.", **PROBLEM},
}


async def visible(services: RestServices, who: Resolution) -> frozenset[str]:
    """The processes the reader may see, by the one predicate of the live representation."""
    reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
    overview = await services.levels.overview(reader)
    return frozenset(p.id for area in overview.areas for p in area.processes)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["acting"])

    @routes.get(
        "/register",
        summary="Everything that acts for the tenant, those that need attention first",
        description="One row per configured worker, connector and model: what it serves, the "
        "processes and steps it acts in with their level and exactness class, whether it is "
        "verified and its last removal verdict, where it processes against the residency rule, "
        "what it used over 28 days, and whether a stop of it is held. Rows that need attention "
        "come first, each with its reasons (ADR-0147 §2). No row names a person.",
        responses={200: {"description": "The register."}, **UNAUTHENTICATED},
    )
    async def register(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.acting.register(who.tenant, await visible(services, who))
        return JSONResponse(found.document())

    @routes.get(
        "/register/inventory",
        summary="The register as an inventory of AI systems, not legally reviewed",
        description="The register in the shape a deployer's inventory of AI systems asks for "
        "under the EU AI Act: per system its purpose, its human oversight, where it processes "
        "and its evidence. Generated from the configuration; `legally_reviewed` is false and "
        "the notice says it is a draft, never a statement of compliance (ADR-0147 §2).",
        responses={200: {"description": "The inventory."}, **UNAUTHENTICATED},
    )
    async def inventory(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        return JSONResponse(
            await services.acting.inventory(who.tenant, await visible(services, who))
        )

    @routes.post(
        "/register/{adapter}/stop",
        summary="Stop an adapter: every run it serves halts at its next step boundary",
        description="Requests the stop of ADR-0138 for the adapter, by you, with no reason. The "
        "stop's rule halts every run at the boundary of a step on the adapter, and runs on "
        "other adapters go on; it is confirmed once it holds. A stop held already is "
        "returned as it is.",
        status_code=202,
        responses={
            202: {
                "description": "The stop, holding until every affected run reached its boundary."
            },
            404: {
                "description": "No configured worker, connector or model of that name.",
                **PROBLEM,
            },
            **UNAUTHENTICATED,
        },
    )
    async def stop(adapter: str, authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            held = await services.acting.stop(who.tenant, adapter, who.identity)
        except NotStoppable as error:
            return problem(404, str(error))
        return JSONResponse(held.document(), status_code=202)

    @routes.get(
        "/dependencies/remove/{adapter}",
        summary="What breaks and what only degrades if an adapter goes",
        description="Every process and step the adapter serves now, marked `breaks` where no "
        "other adapter serves it and no fallback goes to a person, `degrades` where one of them "
        "takes it — by the removal test's own rule, on the configuration as it is now — with the "
        "last removal verdict as evidence (ADR-0147 §3). Acts on nothing.",
        responses={200: {"description": "What depends on the adapter."}, **UNAUTHENTICATED},
    )
    async def remove(
        adapter: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.acting.remove(who.tenant, adapter, await visible(services, who))
        return JSONResponse(found.document())

    @routes.get(
        "/dependencies/wrong-result/{run_id}/{step_id}",
        summary="Where a wrong result went",
        description="Forward from the result of one step of one run, through the provenance "
        "chain: every step run that read it, across runs and processes, with its exactness "
        "class, and what of them left the system. The counts of UC-4.11 this view can give; "
        "the error window is UC-4.11's and is not computed (ADR-0147 §3). Acts on nothing.",
        responses={
            200: {"description": "Where the result went."},
            404: {"description": "No such run, or one you may not see: answered alike.", **PROBLEM},
            **UNAUTHENTICATED,
        },
    )
    async def wrong_result(
        run_id: str, step_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.acting.wrong_result(
            who.tenant, run_id, step_id, await visible(services, who)
        )
        if found is None:
            return problem(404, f"no run {run_id!r} you may see")
        return JSONResponse(found.document())

    @routes.get(
        "/dependencies/residency",
        summary="Where each adapter processes, against the tenant's residency rule",
        responses={200: {"description": "Where data goes."}, **UNAUTHENTICATED},
    )
    async def residency(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.acting.residency(who.tenant, await visible(services, who))
        return JSONResponse(found.document())

    @routes.get(
        "/processes/{process_id}/variants",
        summary="How a process really runs: its variants, its waiting and proposals",
        description="The designed path of the active version, and each variant its ended runs "
        "took — fallbacks to a person, retries, anchor halts, take-overs, how it ended — with "
        "its share and example runs; the waiting at each step by cause; the waiting per role, "
        "shown only where at least two identities hold the role; and proposals a person "
        "decides in a change in dialogue. Read from a projection of the ledger, not the whole "
        "ledger (ADR-0147 §4). No filter by person.",
        responses={
            200: {"description": "The variants."},
            404: {
                "description": "No such process, or one you may not see: answered alike.",
                **PROBLEM,
            },
            **UNAUTHENTICATED,
        },
    )
    async def process_variants(
        process_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if process_id not in await visible(services, who):
            return problem(404, f"no process {process_id!r} you may see")
        found = await services.acting.variants(who.tenant, process_id)
        if found is None:
            return problem(404, f"no process {process_id!r} you may see")
        return JSONResponse(found.document())

    return routes
