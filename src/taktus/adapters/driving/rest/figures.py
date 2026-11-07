"""Views, the export, reports, explanations, the value ledger and a person's own view, on the
HTTP surface (ADR-0241 to ADR-0245).

- `GET /figures?days=` and `GET /figures.csv?days=` — every figure the reader is entitled to:
  the export (UC-5.7).
- `GET /views?days=` — the reader's views with their figures (UC-6.4);
  `GET`/`PUT /views/configuration` — the tenant's views and entitlements, set by `owner`.
- `GET /value/index`, `GET /value/proposals`, `GET /value/transformation` — the bus-factor
  index, the value proposals and the transformation (UC-6.7, UC-9.1, UC-9.3, UC-9.2);
  `GET`/`PUT /value/basis` — the organisation's stated basis, set by a role holding
  `process.steer`, or by `owner` while no role of the tenant holds it (UC-9.1, ADR-0293).
- `GET /reports/definitions`, `PUT /reports/definitions/{id}` and
  `GET /reports/definitions/{id}/now` — reports for a role (UC-6.2).
- `GET /levels/runs/{run}/steps/{step}/explanation` and `GET /summary?days=` (UC-6.5).
- `GET /me/relief`, `PUT /me/relief/settings`, `GET /people/{identity}/relief` (UC-13.5).
- `GET`/`POST /discoveries`, `POST /discoveries/{id}/agree`,
  `POST /discoveries/{id}/stages/{stage}`, `GET /discoveries/interview?mode=` and
  `POST /discoveries/interview` (UC-9.4).

Each needs an account key in `Authorization: Bearer`, or the web app's session. A process the
reader may not see contributes nothing (ADR-0055 §5); no figure names a person.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from taktus.adapters.driving.rest.acting import visible
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.identity.domain.model import Right
from taktus.components.reporting.domain.model.live import Reader
from taktus.components.reporting.domain.model.views import OWNER
from taktus.components.reporting.domain.service import own
from taktus.components.reporting.domain.service import views as selection
from taktus.components.value.domain.model import DiscoveryRefused
from taktus.components.value.domain.model.discovery import Stage
from taktus.components.value.domain.service import discovery
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
DAYS = Query(default=30, ge=1, le=366, description="The period, in days up to now.")
CSV = "text/csv; charset=utf-8"
BODY = Body(...)
STAGES: dict[str, Stage] = {
    "documented": "documented",
    "valued": "valued",
    "decided": "decided",
    "automated": "automated",
}
OPTIONAL_BODY = Body(default_factory=dict)


@dataclass(frozen=True)
class Asked:
    who: Resolution
    reader: Reader
    visible: frozenset[str]


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["figures"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter or a body does not validate.", **PROBLEM},
    }
    owner_only: dict[int | str, dict[str, Any]] = {
        403: {"description": "Only a person holding `owner` sets it.", **PROBLEM}
    }
    steering: dict[int | str, dict[str, Any]] = {
        403: {
            "description": "Only a role holding `process.steer` sets it — `owner` while no role "
            "of the tenant holds it.",
            **PROBLEM,
        }
    }
    unknown: dict[int | str, dict[str, Any]] = {404: {"description": "No such record.", **PROBLEM}}

    async def steers(a: Asked) -> str | None:
        """None when the asker may steer: their roles hold `process.steer`, or no role of the
        tenant holds it yet and they hold `owner` (ADR-0293 §2). Otherwise what they lack."""
        identities = services.identities
        if await identities.granting(a.who.tenant, frozenset({Right.PROCESS_STEER.value})):
            if Right.PROCESS_STEER in await identities.rights(a.who):
                return None
            return f"the value basis needs a role holding {Right.PROCESS_STEER.value}"
        return None if OWNER in a.who.roles else "only a person holding owner states the basis"

    async def asked(authorization: str | None) -> Asked | None:
        who = await authenticated(services, authorization)
        if who is None:
            return None
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        return Asked(who=who, reader=reader, visible=await visible(services, who))

    async def entitled(a: Asked, days: int) -> tuple[list[Any], Any]:
        reading = services.reading
        gathered = await reading.figures.gather(a.reader, a.visible, days)
        configuration = await reading.figures.configuration(a.who.tenant)
        return (
            selection.exported(a.who.roles, configuration, gathered.shown, gathered.holders),
            gathered,
        )

    # --- the export and the views ------------------------------------------------------------

    @routes.get(
        "/figures",
        summary="Every figure the reader is entitled to: the export",
        description="The same figures, definitions and values every view shows, in JSON. A "
        "figure the reader's roles are not entitled to is absent. Each names its owner, "
        "definition, unit, scope, period, value or why it is withheld, method and basis.",
        responses={200: {"description": "The figures."}, **common},
    )
    async def exported(
        days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        figures, gathered = await entitled(a, days)
        return JSONResponse(
            {
                "since": gathered.facts.since.isoformat(),
                "until": gathered.facts.until.isoformat(),
                "figures": [f.model_dump(mode="json") for f in figures],
            }
        )

    @routes.get(
        "/figures.csv",
        summary="Every figure the reader is entitled to, as CSV",
        description="The rows of `GET /figures`, one figure a row, for any "
        "business-intelligence tool.",
        responses={200: {"description": "The CSV.", "content": {CSV: {}}}, **common},
        response_class=Response,
    )
    async def exported_csv(
        days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> Response:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        figures, _ = await entitled(a, days)
        return Response(content=selection.as_csv(figures), media_type=CSV)

    @routes.get(
        "/views",
        summary="The reader's views, each with the figures it shows them",
        description="A view the reader holds by a role or was given by name, showing only the "
        "figures the reader's roles are entitled to. Every figure here is in `GET /figures`.",
        responses={200: {"description": "The views."}, **common},
    )
    async def views(days: int = DAYS, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        reading = services.reading
        gathered = await reading.figures.gather(a.reader, a.visible, days)
        configuration = await reading.figures.configuration(a.who.tenant)
        return JSONResponse(
            {
                "views": selection.shown(
                    a.who.identity, a.who.roles, configuration, gathered.shown, gathered.holders
                )
            }
        )

    @routes.get(
        "/views/configuration",
        summary="The tenant's views and who is entitled to which figure",
        responses={200: {"description": "The configuration."}, **owner_only, **common},
    )
    async def configuration(authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in a.who.roles:
            return problem(403, "only a person holding owner reads the configuration")
        held = await services.reading.figures.configuration(a.who.tenant)
        return JSONResponse(held.document())

    @routes.put(
        "/views/configuration",
        summary="Set the tenant's views and entitlements",
        description="Views, each with its figures, the roles that hold it, the persons it is "
        "given to and what it groups by — never a person; entitlements per figure; depth and "
        "language of an explanation per role. A figure no component computes is refused.",
        responses={200: {"description": "Stored."}, **owner_only, **common},
    )
    async def configure(
        body: dict[str, Any] = BODY, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in a.who.roles:
            return problem(403, "only a person holding owner sets the views")
        try:
            stored = await services.reading.figures.configure(a.who.tenant, body, by=a.who.identity)
        except (ValueError, ValidationError) as error:
            return problem(422, str(error))
        return JSONResponse(stored.document())

    # --- the value ledger ---------------------------------------------------------------------

    @routes.get(
        "/value/index",
        summary="The bus-factor index: without Taktus, per role, per supplier",
        description="Computed from recorded takeover trials and removal verdicts only. With "
        "the trend per day and the graph of dependencies. No figure names a person.",
        responses={200: {"description": "The index."}, **common},
    )
    async def index(days: int = DAYS, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        figures, gathered = await entitled(a, days)
        return JSONResponse(
            {
                "figures": [
                    f.model_dump(mode="json")
                    for f in figures
                    if f.id.startswith("value.bus_factor")
                ],
                "trend": list(gathered.index.trend),
                "graph": list(gathered.index.graph),
            }
        )

    @routes.get(
        "/value/proposals",
        summary="What to do: targets missed, deteriorations, each process's quadrant",
        description="Computed on every read and stored nowhere; nothing changes. A reader sees "
        "the proposals addressed to a role they hold; `owner` sees every one.",
        responses={200: {"description": "The proposals."}, **common},
    )
    async def proposals(days: int = DAYS, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        _, gathered = await entitled(a, days)
        return JSONResponse(
            {
                "proposals": [
                    p.document()
                    for p in gathered.proposals
                    if OWNER in a.who.roles or p.addressed_to in a.who.roles
                ]
            }
        )

    @routes.get(
        "/value/transformation",
        summary="Maturity per unit, progress against the plan, the backlog of potential",
        responses={200: {"description": "The transformation."}, **common},
    )
    async def transformation(
        days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        figures, gathered = await entitled(a, days)
        return JSONResponse(
            {
                "figures": [f.model_dump(mode="json") for f in figures if f.scope == "unit"],
                "index": [
                    f.model_dump(mode="json")
                    for f in figures
                    if f.id == "value.bus_factor.without_taktus"
                ],
                "backlog": gathered.backlog,
            }
        )

    @routes.get(
        "/value/basis",
        summary="The organisation's stated value basis, every version",
        responses={200: {"description": "The versions."}, **steering, **common},
    )
    async def bases(authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        lacking = await steers(a)
        if lacking is not None:
            return problem(403, lacking)
        history = await services.reading.bases.history(a.who.tenant)
        return JSONResponse({"versions": [b.document() for b in history]})

    @routes.put(
        "/value/basis",
        summary="State the next version of the value basis",
        description="Personnel cost rates per role — never per person — and per process the "
        "minutes by hand, the roles, the time to learn, the response by hand, the relevance, "
        "the licence share and the investment; targets; the plan; entered potential.",
        responses={200: {"description": "Stored."}, **steering, **common},
    )
    async def set_basis(
        body: dict[str, Any] = BODY, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        lacking = await steers(a)
        if lacking is not None:
            return problem(403, lacking)
        try:
            stored = await services.reading.bases.set(a.who.tenant, body, by=a.who.identity)
        except (ValueError, ValidationError) as error:
            return problem(422, str(error))
        return JSONResponse(stored.document())

    # --- reports -------------------------------------------------------------------------------

    @routes.get(
        "/reports/definitions",
        summary="The reports for roles: reader, trigger, channel",
        responses={200: {"description": "The definitions."}, **common},
    )
    async def definitions(authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        every = await services.reading.reports.every(a.who.tenant)
        return JSONResponse(
            {
                "definitions": [
                    d.document()
                    for d in every
                    if OWNER in a.who.roles or d.reader_role in a.who.roles
                ]
            }
        )

    @routes.put(
        "/reports/definitions/{report}",
        summary="Set a report: its reader role, its trigger and the channel",
        description="A report without a reader is refused; a schedule needs `every` and "
        "`hour`, a week its `weekday`.",
        responses={200: {"description": "Stored."}, **owner_only, **common},
    )
    async def set_definition(
        report: str,
        body: dict[str, Any] = BODY,
        authorization: str | None = Header(default=None),
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in a.who.roles:
            return problem(403, "only a person holding owner sets a report")
        try:
            stored = await services.reading.reports.put(
                a.who.tenant, {**body, "id": report}, by=a.who.identity
            )
        except (ValueError, ValidationError) as error:
            return problem(422, str(error))
        return JSONResponse(stored.document())

    @routes.get(
        "/reports/definitions/{report}/now",
        summary="The report composed now, for a reader who holds its role",
        description="Its first level carries only what bears on its reader role; a quiet "
        "period is one sentence.",
        responses={200: {"description": "The report."}, **unknown, **common},
    )
    async def now(report: str, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        definition = await services.reading.reports.get(a.who.tenant, report)
        if definition is None or (
            definition.reader_role not in a.who.roles and OWNER not in a.who.roles
        ):
            return problem(404, f"no report {report!r} for you")
        composed = await services.reading.reports.compose(definition, a.visible)
        return JSONResponse(composed.document())

    # --- explanations ---------------------------------------------------------------------------

    @routes.get(
        "/levels/runs/{run}/steps/{step}/explanation",
        summary="Why Taktus did a step the way it did, from the records",
        description="What was done, by which method and why, what was rejected, what it "
        "consumed and what came out — at the depth and in the language of the reader's role. "
        "Every number in it is a number of the records.",
        responses={200: {"description": "The explanation."}, **unknown, **common},
    )
    async def explanation(
        run: str, step: str, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        found = await services.reading.explanations.step(a.reader, run, step)
        if found is None or not found.grounded:
            return problem(404, f"no step {step!r} of a run {run!r}")
        return JSONResponse(found.document())

    @routes.get(
        "/summary",
        summary="What Taktus did in a period, per process",
        responses={200: {"description": "The summary."}, **common},
    )
    async def summary(days: int = DAYS, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        return JSONResponse(await services.reading.explanations.summary(a.reader, a.visible, days))

    # --- a person's own view ----------------------------------------------------------------

    @routes.get(
        "/me/relief",
        summary="What Taktus took off you: tasks, time regained, your goals",
        description="Yours alone unless you share it with a role. No points, levels, ranks "
        "or comparisons.",
        responses={200: {"description": "Your view."}, **common},
    )
    async def mine(days: int = DAYS, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        view = await services.reading.own.relief(a.reader, a.visible, days)
        return JSONResponse(view.document())

    @routes.put(
        "/me/relief/settings",
        summary="Your own view's settings: whom you share it with, your goals, your line",
        responses={200: {"description": "Stored."}, **common},
    )
    async def settings(
        body: dict[str, Any] = BODY, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        try:
            stored = await services.reading.own.set(a.who.tenant, a.who.identity, body)
        except (ValueError, ValidationError) as error:
            return problem(422, str(error))
        return JSONResponse(stored.document())

    @routes.get(
        "/people/{identity}/relief",
        summary="A person's own view, while they share it with a role you hold",
        responses={200: {"description": "Their view."}, **unknown, **common},
    )
    async def theirs(
        identity: str, days: int = DAYS, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        reading = services.reading
        held = await reading.own.settings(a.who.tenant, identity)
        person = await services.identities.identity(a.who.tenant, identity)
        if identity != a.who.identity and not own.may_read(a.who.roles, held):
            return problem(404, "no view shared with you")
        if person is None:
            return problem(404, "no view shared with you")
        reader = Reader(tenant=a.who.tenant, identity=identity, roles=person.roles)
        view = await reading.own.relief(reader, a.visible, days)
        return JSONResponse(view.document())

    # --- discovery ----------------------------------------------------------------------------

    @routes.get(
        "/discoveries/interview",
        summary="The questions of the interview, guided or expert",
        responses={200: {"description": "The questions."}, **common},
    )
    async def interview(
        mode: str = Query(default="guided"), authorization: str | None = Header(default=None)
    ) -> Any:
        if await authenticated(services, authorization) is None:
            return problem(401, NEEDS_KEY)
        try:
            return JSONResponse({"mode": mode, "questions": discovery.questions(mode)})
        except ValueError as error:
            return problem(422, str(error))

    @routes.post(
        "/discoveries/interview",
        summary="Write the documented process from the interview's answers",
        description="The same answers give the same documented process in either mode.",
        responses={200: {"description": "The documented process."}, **common},
    )
    async def interviewed(
        body: dict[str, Any] = BODY, authorization: str | None = Header(default=None)
    ) -> Any:
        if await authenticated(services, authorization) is None:
            return problem(401, NEEDS_KEY)
        try:
            return JSONResponse(discovery.documented(body.get("answers") or {}).document())
        except ValueError as error:
            return problem(422, str(error))

    @routes.get(
        "/discoveries",
        summary="Processes nobody wrote down, at their stage",
        description="The organisation's, and the patterns found for you, which only you see.",
        responses={200: {"description": "The discovered processes."}, **common},
    )
    async def discoveries(authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        found = await services.reading.discoveries.of(a.who.tenant, a.who.identity)
        return JSONResponse({"discoveries": [d.document() for d in found]})

    @routes.post(
        "/discoveries",
        summary="Make a process visible",
        description="`origin` is `interview`, `pattern` or `request`. A pattern is found for "
        "you and stays yours until you agree.",
        responses={200: {"description": "Recorded."}, **common},
    )
    async def discover(
        body: dict[str, Any] = BODY, authorization: str | None = Header(default=None)
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        origin = str(body.get("origin", ""))
        try:
            found = await services.reading.discoveries.visible(
                a.who.tenant,
                title=str(body.get("title", "")),
                origin=origin,
                found=str(body.get("found", "")),
                reader=a.who.identity if origin == "pattern" else None,
                by=a.who.identity,
            )
        except (ValueError, ValidationError) as error:
            return problem(422, str(error))
        return JSONResponse(found.document())

    @routes.post(
        "/discoveries/{id}/agree",
        summary="Agree that a pattern found for you becomes the organisation's procedure",
        responses={200: {"description": "Shared."}, **unknown, **common},
    )
    async def agree(id: str, authorization: str | None = Header(default=None)) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        try:
            found = await services.reading.discoveries.agree(a.who.tenant, id, a.who.identity)
        except DiscoveryRefused as error:
            return problem(404 if error.reason == "unknown" else 409, error.detail)
        return JSONResponse(found.document())

    @routes.post(
        "/discoveries/{id}/stages/{stage}",
        summary="Take a discovered process to its next stage",
        description="documented (description, owner_role), valued (minutes_by_hand, "
        "cases_per_month), decided (decision: automate or keep — a person's), automated "
        "(process_id, level 1 or 2, instructions). A stage out of order is refused.",
        responses={
            200: {"description": "Recorded."},
            409: {"description": "Refused: out of order or incomplete.", **PROBLEM},
            **unknown,
            **common,
        },
    )
    async def advance(
        id: str,
        stage: str,
        body: dict[str, Any] = OPTIONAL_BODY,
        authorization: str | None = Header(default=None),
    ) -> Any:
        a = await asked(authorization)
        if a is None:
            return problem(401, NEEDS_KEY)
        if stage not in STAGES:
            return problem(422, f"no stage {stage!r}")
        try:
            found = await services.reading.discoveries.advance(
                a.who.tenant,
                id,
                STAGES[stage],
                a.who.identity,
                **body,
            )
        except DiscoveryRefused as error:
            return problem(404 if error.reason == "unknown" else 409, error.detail)
        return JSONResponse(found.document())

    return routes
