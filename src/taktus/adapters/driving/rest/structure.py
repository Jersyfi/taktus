"""The organisation's structure, its projects and their sessions on the HTTP surface (ADR-0275,
ADR-0276, ADR-0277, ADR-0279; UC-1.4, UC-1.6, UC-1.8).

- `GET /structure` — the levels, the units the reader may see (no private project but their
  own), and where each object they see is placed.
- `PUT /structure/levels`, `POST /structure/units`, `PUT /structure/placements/{kind}/{object}`,
  `PUT /structure/knowledge/{unit}` — shaping the structure, for a role holding
  `structure.shape`; each act is a ledger entry naming who did it.
- `GET /structure/filings/{kind}/{object}` — where something Taktus set up is documented, every
  place with its link.
- `GET /projects`, `POST /projects`, `POST /projects/{project}/share`,
  `POST /projects/{project}/references` — the reader's projects, created for a circle within
  their rights, shared by their owner alone, referring to what they bring together.
- `POST /projects/{project}/session`, `POST /sessions/{session}/turns`,
  `POST /sessions/{session}/plan`, `POST /sessions/{session}/close` — the reader's session in a
  project: the same one on every channel, every statement with its source.

Each needs an account key in `Authorization: Bearer`, or the web app's session.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.inventory import read_recorded
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.command.application.service.sessions import SessionError
from taktus.components.identity.application.service.structure import OrganisationStructure
from taktus.components.identity.domain.model import Right
from taktus.components.identity.domain.model.structure import Circle, PlacedKind, Reference
from taktus.components.identity.domain.service import structure as rules
from taktus.components.identity.domain.service.structure import StructureRefused
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
NOT_SHAPED = "shaping the structure needs a role holding structure.shape"
NO_STRUCTURE = "this instance keeps no organisational structure"


class LevelsBody(BaseModel):
    levels: list[str] = Field(min_length=2, max_length=8)


class UnitBody(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parent: str = Field(min_length=1)


class PlaceBody(BaseModel):
    unit: str = Field(min_length=1)


class KnowledgeBody(BaseModel):
    base: str = Field(min_length=1, description="The link documentation is filed under.")


class ProjectBody(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    circle: Circle
    unit: str | None = None
    members: list[str] = Field(default_factory=list)


class ShareBody(BaseModel):
    circle: Circle
    unit: str | None = None


class SayBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    channel: str = Field(default="channel.web")


class SettleBody(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["structure"])
    common: dict[int | str, dict[str, Any]] = {
        400: {"description": "Refused; the detail says why.", **PROBLEM},
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        403: {"description": "Your roles do not hold the right.", **PROBLEM},
        404: {"description": "This instance keeps no structure.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    def org() -> OrganisationStructure:
        """The structure, once `reader` or `shaper` answered that the instance keeps one."""
        found = services.structure
        if found is None:
            raise LookupError(NO_STRUCTURE)
        return found

    async def shaper(authorization: str | None) -> Resolution | JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if services.structure is None:
            return problem(404, NO_STRUCTURE)
        if Right.SHAPE_STRUCTURE not in await services.identities.rights(who):
            return problem(403, NOT_SHAPED)
        return who

    async def reader(authorization: str | None) -> Resolution | JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if services.structure is None:
            return problem(404, NO_STRUCTURE)
        return who

    @routes.get(
        "/structure",
        summary="The organisation's structure",
        description="Its levels, the units you may see — no private project but your own — and "
        "where every object you see is placed (ADR-0275).",
        responses={200: {"description": "The structure."}, **common},
    )
    async def shown(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        structure = org()
        levels = await structure.levels(who.tenant)
        units = await structure.units(who.tenant)
        own = rules.belongs(units, who.identity, who.org_path)
        seen = {u.id: u for u in units.values() if not u.private or u.id in own}
        unseen = set(who.unseen)
        placements = [
            p.document()
            for p in await structure.placements(who.tenant)
            if p.unit in seen and not (p.kind is PlacedKind.PROCESS and p.object in unseen)
        ]
        await read_recorded(
            services.ledger, services.work, who.tenant, "structure.show", who.identity
        )
        return JSONResponse(
            {
                "levels": list(levels.levels),
                "units": [
                    u.document() for u in sorted(seen.values(), key=lambda u: (u.level, u.id))
                ],
                "placements": placements,
                "yours": sorted(own),
            }
        )

    @routes.put(
        "/structure/levels",
        summary="Name the structure's levels",
        description="The root's first; refused while a unit sits deeper than the names reach.",
        responses={200: {"description": "The levels."}, **common},
    )
    async def name_levels(
        body: LevelsBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await shaper(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            named = await org().name_levels(who.tenant, body.levels, by=who.identity)
        except (StructureRefused, ValueError) as error:
            return problem(400, str(error))
        return JSONResponse(named.document())

    @routes.post(
        "/structure/units",
        summary="Add a unit",
        description="One level below its parent, never below the last level.",
        status_code=201,
        responses={201: {"description": "The unit."}, **common},
    )
    async def add_unit(
        body: UnitBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await shaper(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            added = await org().add_unit(
                who.tenant, body.id, body.name, body.parent, by=who.identity
            )
        except (StructureRefused, ValueError) as error:
            return problem(400, str(error))
        return JSONResponse(added.document(), status_code=201)

    @routes.put(
        "/structure/placements/{kind}/{name}",
        summary="Place or move an object",
        description="The object is in the unit from now on, and only there; what it is seen "
        "by, what it uses and where its next runs count follow (ADR-0275).",
        responses={200: {"description": "The placement."}, **common},
    )
    async def place(
        kind: PlacedKind,
        name: str,
        body: PlaceBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        units = await org().units(who.tenant)
        target = units.get(body.unit)
        # Placing in a project of one's own is the owner's act; anything else shapes.
        own_project = (
            target is not None
            and target.project
            and target.id in rules.belongs(units, who.identity, who.org_path)
        )
        if not own_project and Right.SHAPE_STRUCTURE not in await services.identities.rights(who):
            return problem(403, NOT_SHAPED)
        try:
            placed = await org().place(who.tenant, kind, name, body.unit, by=who.identity)
        except StructureRefused as error:
            return problem(400, str(error))
        return JSONResponse(placed.document())

    @routes.put(
        "/structure/knowledge/{unit}",
        summary="Configure a unit's knowledge system",
        description="Documentation of the unit, and of every unit below it without one, is "
        "filed there from now on, and that system is the record (ADR-0275 §7).",
        responses={200: {"description": "The unit's knowledge system."}, **common},
    )
    async def knowledge(
        unit: str, body: KnowledgeBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await shaper(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            home = await org().configure_knowledge(who.tenant, unit, body.base, by=who.identity)
        except StructureRefused as error:
            return problem(400, str(error))
        return JSONResponse(home.document())

    @routes.get(
        "/structure/filings/{kind}/{name}",
        summary="Where something is documented",
        description="Every place, each with the link that opens it.",
        responses={200: {"description": "The filing."}, **common},
    )
    async def where(
        kind: PlacedKind, name: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        if kind is PlacedKind.PROCESS and name in who.unseen:
            return problem(404, f"nothing filed for {name!r} that you may see")
        found = await org().where(who.tenant, kind, name)
        await read_recorded(
            services.ledger, services.work, who.tenant, "structure.where", who.identity
        )
        if found is None:
            return problem(404, f"nothing filed for {name!r}")
        return JSONResponse(found.document())

    # --- projects ---------------------------------------------------------------------------

    @routes.get(
        "/projects",
        summary="Your projects",
        description="The projects you belong to, and the shared ones your context sees.",
        responses={200: {"description": "The projects."}, **common},
    )
    async def projects(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        found = await org().projects(who.tenant, who.identity, who.org_path)
        return JSONResponse({"projects": [p.document() for p in found]})

    @routes.post(
        "/projects",
        summary="Create a project",
        description="Alone (private), for a team you belong to, for a project team, or for the "
        "company with a role holding project.company (ADR-0276).",
        status_code=201,
        responses={201: {"description": "The project."}, **common},
    )
    async def create(
        body: ProjectBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            made = await org().create_project(
                who.tenant,
                body.id,
                body.name,
                body.circle,
                by=who.identity,
                unit=body.unit,
                members=body.members,
            )
        except (StructureRefused, ValueError) as error:
            return problem(400, str(error))
        return JSONResponse(made.document(), status_code=201)

    @routes.post(
        "/projects/{project}/share",
        summary="Share your private project",
        description="With a team you belong to or a project team; only its owner shares it.",
        responses={200: {"description": "The project."}, **common},
    )
    async def share(
        project: str, body: ShareBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            shared = await org().share(
                who.tenant, project, body.circle, by=who.identity, unit=body.unit
            )
        except StructureRefused as error:
            return problem(400, str(error))
        return JSONResponse(shared.document())

    @routes.post(
        "/projects/{project}/references",
        summary="Refer to something of the organisation's own",
        description="The project keeps the link — a ticket, a document — and copies nothing.",
        responses={200: {"description": "The project."}, **common},
    )
    async def refer(
        project: str, body: Reference, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            referred = await org().refer(who.tenant, project, body, by=who.identity)
        except StructureRefused as error:
            return problem(400, str(error))
        return JSONResponse(referred.document())

    # --- sessions ---------------------------------------------------------------------------

    @routes.post(
        "/projects/{project}/session",
        summary="Open your session in a project",
        description="The one you had there before, with its history, on whatever channel; a "
        "new one the first time (ADR-0277).",
        responses={200: {"description": "The session."}, **common},
    )
    async def open_session(
        project: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        if services.sessions is None:
            return problem(404, NO_STRUCTURE)
        try:
            session = await services.sessions.open(who.tenant, project, who.identity)
        except SessionError as error:
            return problem(400, str(error))
        return JSONResponse(session.document())

    @routes.post(
        "/sessions/{session_id}/turns",
        summary="Say something in your session",
        description="Taktus's answer is drawn from the project's knowledge you may see; every "
        "statement names its source, or says it has none. Nothing is acted on.",
        responses={200: {"description": "Taktus's answer."}, **common},
    )
    async def say(
        session_id: str, body: SayBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        if services.sessions is None:
            return problem(404, NO_STRUCTURE)
        try:
            turn = await services.sessions.say(
                who.tenant, session_id, who.identity, body.channel, body.text
            )
        except SessionError as error:
            return problem(400, str(error))
        return JSONResponse({**turn.document(), "shown": [s.shown() for s in turn.statements]})

    @routes.post(
        "/sessions/{session_id}/plan",
        summary="Settle the session in a plan draft",
        description="A draft of the plan dialogue, commissioned there or not at all (UC-1.2).",
        responses={200: {"description": "The outcome."}, **common},
    )
    async def to_plan(
        session_id: str, body: SettleBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        if services.sessions is None:
            return problem(404, NO_STRUCTURE)
        try:
            outcome = await services.sessions.to_plan(
                who.tenant, session_id, who.identity, body.goal, who.org_path, "channel.web"
            )
        except SessionError as error:
            return problem(400, str(error))
        return JSONResponse(outcome.document())

    @routes.post(
        "/sessions/{session_id}/close",
        summary="Close your session",
        description="Opening it again continues it.",
        responses={200: {"description": "The session."}, **common},
    )
    async def close(session_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await reader(authorization)
        if isinstance(who, JSONResponse):
            return who
        if services.sessions is None:
            return problem(404, NO_STRUCTURE)
        try:
            closed = await services.sessions.close(who.tenant, session_id, who.identity)
        except SessionError as error:
            return problem(400, str(error))
        return JSONResponse(closed.document())

    return routes
