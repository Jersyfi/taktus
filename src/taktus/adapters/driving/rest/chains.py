"""End-to-end chains across domains, on the HTTP surface (UC-15.4, ADR-0301 §4, ADR-0302 §3).

- `GET /chains` — every declared chain with its latest run.
- `GET /chains/{chain}` — one chain: its links, what passes at every boundary with its clause,
  its objectives, and its runs, newest first.
- `PUT /chains/{chain}` — the chain declared: held to the versions it links, then stored.
- `POST /chains/{chain}/runs` — the chain started with its inputs.
- `POST /chain-runs/{id}/decision` — a person's decision on a halted chain: the lacking items
  given, or the chain stopped.

Each needs an account key in `Authorization: Bearer`, or the web app's session. A reader sees a
chain only where they may see every process it links (ADR-0055 §5). Only a person who holds the
role `owner` declares, starts or decides one (NTC-0277). No figure names a person.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from taktus.adapters.driving.rest.acting import visible
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.domain.model import InvalidProcess
from taktus.components.process.domain.model.chain import (
    Chain,
    ChainRefused,
    ChainRun,
    DeclaredChain,
)
from taktus.components.reporting.domain.model.trace import OWNER
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class ChainBody(BaseModel):
    name: str = Field(min_length=1, description="The chain's name, as people call it.")
    links: list[dict[str, Any]] = Field(
        min_length=2,
        description="The process versions it links, in order: `{process_version, handover}`, "
        "where `handover` lists each item the link is given — `input`, `step`, `select`, "
        "`clause` — and is empty for the first link.",
    )
    slo: dict[str, Any] | None = Field(
        default=None,
        description="The chain's own objectives: `latency` (an ISO 8601 duration) for one run "
        "of the whole chain, `completion` the least share of its ended runs that finish.",
    )
    escalation: dict[str, Any] | None = Field(
        default=None,
        description="Who a halted handover reaches: `role`, `react_within`, `path`. Without "
        "it, the role `owner` in the owner-facing channel.",
    )


class StartBody(BaseModel):
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="The inputs of the chain's first link."
    )


class DecisionBody(BaseModel):
    given: dict[str, Any] | None = Field(
        default=None,
        description="A value for exactly the items the halted handover lacked; the chain goes "
        "on with them, each marked as given by a person.",
    )
    stop: bool = Field(default=False, description="Stop the chain instead.")


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["chains"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }
    acting: dict[int | str, dict[str, Any]] = {
        403: {"description": "You do not hold the role `owner`.", **PROBLEM},
        404: {"description": "No such chain, or one you may not see.", **PROBLEM},
        **common,
    }

    async def seen(who: Resolution) -> Callable[[Chain], bool]:
        processes = await visible(services, who)

        def may(chain: Chain) -> bool:
            return all(link.process_version.split("@", 1)[0] in processes for link in chain.links)

        return may

    @routes.get(
        "/chains",
        summary="The chains across domains, each with its latest run",
        description="Every chain the tenant declared that links only processes the reader may "
        "see: its links in order and its latest run with its state.",
        responses={200: {"description": "The chains."}, **common},
    )
    async def listed(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        may = await seen(who)
        shown: list[dict[str, Any]] = []
        for declared in await services.chains.chains(who.tenant):
            if not may(declared.chain):
                continue
            runs = await services.chains.runs_of(who.tenant, declared.id)
            shown.append(_declared(declared, runs[:1]))
        return JSONResponse({"chains": shown})

    @routes.get(
        "/chains/{chain}",
        summary="One chain as a whole",
        description="Its links in order, what passes at every boundary with the clause that "
        "requires it, its objectives and who its halt reaches, and every run of it, newest "
        "first: the link it stands at, the run of every link, every handover by digest, and "
        "why it waits, halted or stopped.",
        responses={200: {"description": "The chain."}, 404: acting[404], **common},
    )
    async def one(chain: str, authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        declared = await services.chains.chain(who.tenant, chain)
        if declared is None or not (await seen(who))(declared.chain):
            return problem(404, f"no chain {chain!r}")
        runs = await services.chains.runs_of(who.tenant, chain)
        return JSONResponse(_declared(declared, runs))

    @routes.put(
        "/chains/{chain}",
        summary="Declare a chain across domains",
        description="The process versions it links, in order, and at each boundary every item "
        "handed over with its clause. It is held to the versions it links: every input the "
        "receiving version requires given by exactly one item, every item from a step of the "
        "sending version. A new declaration replaces the one before; a run keeps its own.",
        responses={200: {"description": "The chain as declared."}, **acting},
    )
    async def declare(
        chain: str, body: ChainBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in who.roles:
            return problem(403, f"only the role {OWNER!r} declares a chain")
        try:
            parsed = Chain.model_validate({"id": chain, **body.model_dump(exclude_none=True)})
        except ValidationError as error:
            return problem(422, _said(error))
        try:
            declared = await services.chains.declare(who.tenant, parsed)
        except InvalidProcess as error:
            return problem(422, str(error))
        return JSONResponse(_declared(declared, []))

    @routes.post(
        "/chains/{chain}/runs",
        summary="Start a chain",
        description="The first link starts with the inputs given. The chain runs link by link "
        "until a link does not finish, a handover halts, or the last link ended, and is "
        "answered as it then stands. A chain that waits goes on by itself once its link "
        "finished.",
        responses={200: {"description": "The chain run."}, **acting},
    )
    async def start(
        chain: str, body: StartBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in who.roles:
            return problem(403, f"only the role {OWNER!r} starts a chain")
        declared = await services.chains.chain(who.tenant, chain)
        if declared is None or not (await seen(who))(declared.chain):
            return problem(404, f"no chain {chain!r}")
        try:
            run = await services.chains.started(who.tenant, chain, body.inputs, who.identity)
        except InvalidProcess as error:
            return problem(422, str(error))
        return JSONResponse(run.document())

    @routes.post(
        "/chain-runs/{chain_run}/decision",
        summary="Decide on a halted chain",
        description="`given`: a value for exactly the items the halted handover lacked; the "
        "chain hands them over, marked as given by a person, and goes on. `stop`: the chain "
        "stops, and the links before keep their results. Taktus fills in nothing itself.",
        responses={
            200: {"description": "The chain run as it now stands."},
            409: {"description": "The decision does not fit the chain run's state.", **PROBLEM},
            **acting,
        },
    )
    async def decide(
        chain_run: str, body: DecisionBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if OWNER not in who.roles:
            return problem(403, f"only the role {OWNER!r} decides on a chain")
        found = await services.chains.chain_run(who.tenant, chain_run)
        if found is None or not (await seen(who))(found.chain):
            return problem(404, f"no chain run {chain_run!r}")
        if body.stop == (body.given is not None):
            return problem(422, "a decision gives the lacking items, or stops the chain")
        try:
            run = await services.chains.decided(
                who.tenant, chain_run, who.identity, given=body.given, stop=body.stop
            )
        except ChainRefused as error:
            return problem(409, str(error))
        except InvalidProcess as error:
            return problem(422, str(error))
        return JSONResponse(run.document())

    return routes


def _declared(declared: DeclaredChain, runs: list[ChainRun]) -> dict[str, Any]:
    return {
        **declared.chain.document(),
        "declared_at": declared.declared_at.isoformat(),
        "runs": [run.model_dump(mode="json", exclude={"chain"}) for run in runs],
    }


def _said(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'chain'}: {e['msg']}" for e in error.errors()
    )
