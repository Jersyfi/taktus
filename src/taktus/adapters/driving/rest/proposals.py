"""A person's proposals for a changed process, on the HTTP surface (UC-4.15, ADR-0091 §6).

- `POST /processes/{process_id}/proposals` — a changed bundle becomes a proposal, never a version.
- `GET /processes/{process_id}/proposals` — the process's proposals, newest first.
- `GET /processes/{process_id}/proposals/{proposal_id}` — one proposal, with its difference.
- `POST /processes/{process_id}/proposals/{proposal_id}/discard` — an open proposal, discarded.

Each needs an account key in `Authorization: Bearer`. A process of another tenant, or one that
does not exist, is answered `404` alike. Until rights per role exist (UC-7.3), an identity the
tenant knows may propose, as it may register a version by hand. Nothing here registers anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.process.application.service.proposals import ProposalError, Propose
from taktus.components.process.domain.model import InvalidProcess, Proposal
from taktus.components.process.domain.model.evaluation import Evaluation
from taktus.components.process.domain.service import scoring
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


class ProposeBody(BaseModel):
    bundle: dict[str, Any] | None = Field(
        default=None,
        description="The changed process bundle, as a document. Without it, `request` is turned "
        "into a proposal by the process the instance names for it, and the answer names that "
        "run (ADR-0091 §2).",
    )
    request: str | None = Field(
        default=None, min_length=1, description="The words the change was asked for in."
    )


def _view(proposal: Proposal) -> dict[str, Any]:
    return proposal.document()


def evaluated_view(evaluation: Evaluation) -> dict[str, Any]:
    """An evaluation as the change page and the owner's conversation read it: its verdict and
    sides, and every case compared (ADR-0134 §9). An override carries its reason and when; the
    person is the actor of `evaluation.overridden`, never a field here (principle 14)."""
    document = evaluation.document()
    view = {
        key: document.get(key)
        for key in (
            "id",
            "purpose",
            "state",
            "verdict",
            "tolerance",
            "sides",
            "override",
            "started_at",
            "scored_at",
        )
    }
    view["scorers"] = [
        {
            "step": s.step,
            "method": s.method.value,
            "exactness": s.exactness.value,
            "rule": None if s.rule is None else s.rule.kind,
        }
        for s in evaluation.scorers
    ]
    view["cases"] = list(scoring.comparison(evaluation))
    return view


def _refused(error: ProposalError) -> JSONResponse:
    return problem(404 if error.kind == "unknown" else 409, str(error))


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["proposals"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such process or proposal you may see.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.post(
        "/processes/{process_id}/proposals",
        summary="Propose a changed process",
        description="The changed bundle becomes a proposal, made against the active version, with "
        "its difference step by step. Nothing is registered: the active version, its triggers and "
        "its runs are unchanged. A bundle that would not register is answered with the findings "
        "registration would give, and nothing is kept (ADR-0091 §1).",
        responses={
            201: {"description": "The proposal."},
            202: {"description": "Asked in words: the run that makes the proposal."},
            400: {"description": "The bundle would not register; every finding.", **PROBLEM},
            **common,
        },
    )
    async def propose(
        process_id: str, body: ProposeBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if body.bundle is None:
            if body.request is None:
                return problem(422, "give the changed bundle, or the change in your own words")
            try:
                run = await services.proposal_acts.ask(
                    who.tenant, process_id, body.request, who.identity
                )
            except ProposalError as error:
                return _act_refused(error)
            return JSONResponse({"run": run.id}, status_code=202)
        try:
            made = await services.proposals.propose(
                Propose(
                    tenant=who.tenant,
                    process_id=process_id,
                    bundle=body.bundle,
                    by=who.identity,
                    request=body.request,
                )
            )
        except ProposalError as error:
            return _refused(error)
        except InvalidProcess as error:
            return problem(400, "the bundle would not register", findings=list(error.findings))
        return JSONResponse(_view(made), status_code=201)

    @routes.get(
        "/processes/{process_id}/proposals",
        summary="The proposals for a process",
        responses={200: {"description": "The proposals, newest first."}, **common},
    )
    async def proposals(
        process_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        found = await services.proposals.of_process(who.tenant, process_id)
        return JSONResponse({"proposals": [_view(p) for p in found]})

    @routes.get(
        "/processes/{process_id}/proposals/{proposal_id}",
        summary="One proposal, with its difference",
        description="The proposal, and where it was rehearsed beside the active version on the "
        "process's evaluation cases, that evaluation under `evaluated`: its state, verdict, "
        "tolerance and the score of each side, every case with its sides beside each other, "
        "and an override's reason. Who overrode is the ledger's, never the view's (ADR-0134 §9, "
        "principle 14).",
        responses={200: {"description": "The proposal."}, **common},
    )
    async def one(
        process_id: str, proposal_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            found = await services.proposals.get(who.tenant, process_id, proposal_id)
        except ProposalError as error:
            return _refused(error)
        view = _view(found)
        if found.evaluation is not None:
            try:
                evaluated = await services.evaluations.get(who.tenant, process_id, found.evaluation)
            except ProposalError:
                return JSONResponse(view)
            view["evaluated"] = evaluated_view(evaluated)
        return JSONResponse(view)

    @routes.post(
        "/processes/{process_id}/proposals/{proposal_id}/discard",
        summary="Discard a proposal",
        description="An open proposal is discarded; nothing else changes.",
        responses={
            200: {"description": "The proposal, discarded."},
            409: {"description": "The proposal is no longer open.", **PROBLEM},
            **common,
        },
    )
    async def discard(
        process_id: str, proposal_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            discarded = await services.proposals.discard(who.tenant, process_id, proposal_id)
        except ProposalError as error:
            return _refused(error)
        return JSONResponse(_view(discarded))

    return routes


class RehearseBody(BaseModel):
    inputs: dict[str, Any] | None = Field(
        default=None,
        description="What the rehearsal is given; without it, the active version's last run's.",
    )


class ApproveBody(BaseModel):
    approve_raise: bool = Field(
        default=False,
        description="True: you approve a raise of an autonomy level the version makes (ADR-0026).",
    )


class CommissionBody(ApproveBody):
    override: str | None = Field(
        default=None,
        min_length=1,
        description="Your reason for commissioning against the verdict of the proposal's "
        "evaluation on the process's cases: a regression, or a case without a score. Recorded "
        "with the reason (ADR-0134 §4).",
    )


class RollbackBody(ApproveBody):
    version: str = Field(min_length=1, description="The earlier version to make current again.")
    as_version: str | None = Field(
        default=None, min_length=1, description="The new version's name; the next free one if none."
    )


STATUS = {"unknown": 404}
"""Every other refusal of an act is a conflict with the proposal's or the process's state."""


def _act_refused(error: ProposalError) -> JSONResponse:
    return problem(STATUS.get(error.kind, 409), str(error), kind=error.kind)


def acts_router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["proposals"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        404: {"description": "No such process, proposal or version you may see.", **PROBLEM},
        409: {
            "description": "The act does not fit the proposal's or the process's state.",
            **PROBLEM,
        },
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    @routes.post(
        "/processes/{process_id}/proposals/{proposal_id}/rehearse",
        summary="Rehearse a proposal",
        description="The proposed version runs as a rehearsal: no outward operation acts, each "
        "answers from the recording of its last real call (ADR-0030). The run counts as no "
        "version. Read it at `/levels/runs/{run_id}` (ADR-0091 §3).",
        responses={202: {"description": "The proposal, and the rehearsal run."}, **common},
    )
    async def rehearse(
        process_id: str,
        proposal_id: str,
        body: RehearseBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            proposal, run = await services.proposal_acts.rehearse(
                who.tenant, process_id, proposal_id, who.identity, body.inputs
            )
        except ProposalError as error:
            return _act_refused(error)
        return JSONResponse({"proposal": _view(proposal), "run": run.id}, status_code=202)

    @routes.post(
        "/processes/{process_id}/proposals/{proposal_id}/commission",
        summary="Commission a proposal",
        description="A proposal whose rehearsal finished is registered as the active version, "
        "acting for you, through registration and every check it applies. A proposal that "
        "changes a step of a process with evaluation cases is registered only once its "
        "evaluation passed, or with your reason against its verdict (ADR-0134 §4). The ledger "
        "records `process.commissioned` with you as its actor (ADR-0091 §4).",
        responses={
            200: {"description": "The version registered."},
            400: {"description": "Registration refused it; every finding.", **PROBLEM},
            **common,
        },
    )
    async def commission(
        process_id: str,
        proposal_id: str,
        body: CommissionBody,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            version = await services.proposal_acts.commission(
                who.tenant,
                process_id,
                proposal_id,
                who.identity,
                approved_by=who.identity if body.approve_raise else None,
                override=body.override,
            )
        except ProposalError as error:
            return _act_refused(error)
        except InvalidProcess as error:
            return problem(400, "registration refused it", findings=list(error.findings))
        return JSONResponse({"process": process_id, "version": version.version})

    @routes.post(
        "/processes/{process_id}/rollback",
        summary="Roll a process back to an earlier version",
        description="The earlier version's content is registered again as a new version, "
        "through registration, acting for you. Nothing is deleted; a run under way finishes on "
        "its version. The ledger records `process.rolled_back` (ADR-0091 §5).",
        responses={
            200: {"description": "The version registered."},
            400: {"description": "Registration refused it; every finding.", **PROBLEM},
            **common,
        },
    )
    async def rollback(
        process_id: str, body: RollbackBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        try:
            version = await services.proposal_acts.rollback(
                who.tenant,
                process_id,
                body.version,
                who.identity,
                as_version=body.as_version,
                approved_by=who.identity if body.approve_raise else None,
            )
        except ProposalError as error:
            return _act_refused(error)
        except InvalidProcess as error:
            return problem(400, "registration refused it", findings=list(error.findings))
        return JSONResponse({"process": process_id, "version": version.version})

    return routes
