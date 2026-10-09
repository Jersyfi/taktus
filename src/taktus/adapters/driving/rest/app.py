"""The FastAPI application: every route under the configured prefix.

Health and readiness are two different questions. `/health` says the process is alive — it
answers, therefore it is — and a platform restarts a process that stops answering it.
`/ready` says the process may receive traffic: the database answers and its schema is the one
this build needs. A role that has lost its database is not ready and must not receive traffic;
it is not therefore unhealthy, and restarting it in a loop would only make the outage louder.

The `api` role adds the rest: webhook intake for the channel a connector serves, the completion
of an intake event into a command by the identity the identity component places, the link code
a person creates in their Taktus account to link a channel account (ADR-0040), the decision
requests addressed to a decider — listed, answered, the reading confirmed — and the decider's
own response times (ADR-0042), the reports to the owner as their view and their repository
text (ADR-0045), and a read API for runs and ledger entries. No other write, no UI. An answer
the owner writes in the thread of a report arrives through the webhook intake.

The prefix is applied to every route literally, so that an instance placed under a sub-path by
the platform works whether or not the platform strips the prefix before forwarding, and every
link it produces is right. The OpenAPI document (`api/openapi.yaml`, `make generate`) is
generated at the root and names the prefix as a server variable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from taktus.adapters.driving.rest.problems import on_http_exception, on_validation_error, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.command.application.service import (
    AlreadyCompleted,
    CompleteIntake,
    ReceiveIntake,
    UnknownChannel,
    UnknownIntakeEvent,
    UnknownSender,
)
from taktus.components.decision.application.query import Addressed
from taktus.components.decision.application.service import (
    AnswerRequest,
    ConfirmRequest,
    DecisionError,
    NotAnswerable,
    NotTheDecider,
    UnknownRequest,
)
from taktus.components.identity.application.service import UnknownIdentity
from taktus.components.reporting.application.query import view as report_view
from taktus.components.reporting.domain.service.rendering import repository_text
from taktus.ports.connector import ConnectorError, Delivery, RefusalReason
from taktus.ports.identity import Resolution
from taktus.shared.v1.capability import CAPABILITY_PATTERN

VERSION = "0.1.0"
PROBLEM: dict[str, Any] = {"content": {"application/problem+json": {}}}
INVALID: dict[int | str, dict[str, Any]] = {
    422: {"description": "A parameter does not validate.", **PROBLEM}
}

# A refusal the sender should correct — no signature, a wrong one, a body that cannot be
# read — is answered with the status that says so; the rest are the sender's business
# fulfilled: the delivery was received and decided upon.
REFUSAL_STATUS = {
    RefusalReason.UNSIGNED: 401,
    RefusalReason.BAD_SIGNATURE: 401,
    RefusalReason.MALFORMED: 400,
    RefusalReason.UNSUPPORTED_EVENT: 202,
    RefusalReason.OWN_ACTION: 202,
}


def build_app(services: RestServices, *, prefix: str = "/", full: bool = True) -> FastAPI:
    """`full` is the `api` role: without it a process serves health and readiness only."""
    base = "" if prefix == "/" else prefix.rstrip("/")
    app = FastAPI(
        title="Taktus",
        version=VERSION,
        description="An operating layer for a business — the control plane's own interface.",
        openapi_url=f"{base}/openapi.json",
        docs_url=None,
        redoc_url=None,
        servers=[
            {
                "url": "{prefix}",
                "description": "The path prefix the instance is served under (TAKTUS_PATH_PREFIX).",
                "variables": {"prefix": {"default": "/"}},
            }
        ],
    )
    app.add_exception_handler(HTTPException, on_http_exception)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.include_router(_operations(services), prefix=base)
    if full:
        app.include_router(_intake(services), prefix=base)
        app.include_router(_identity(services), prefix=base)
        app.include_router(_decisions(services), prefix=base)
        app.include_router(_owner(services), prefix=base)
        app.include_router(_reads(services), prefix=base)
    return app


def _operations(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["operations"])

    @router.get(
        "/health",
        summary="Liveness: the process is alive",
        responses={200: {"description": "The process answers."}},
    )
    async def health() -> dict[str, Any]:
        return {"status": "alive"}

    @router.get(
        "/ready",
        summary="Readiness: the process may receive traffic",
        responses={
            200: {"description": "The database answers and is at the schema this build needs."},
            503: {"description": "Not ready; the problem's detail says why.", **PROBLEM},
        },
    )
    async def ready() -> JSONResponse:
        reason = await services.ready()
        if reason is not None:
            return problem(503, reason, title="Not ready")
        return JSONResponse(
            {"status": "ready", "roles": list(services.roles), "leading": services.leading}
        )

    return router


def _intake(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["intake"])

    @router.post(
        "/intake/{channel}",
        summary="Webhook intake for a channel",
        description="The delivery as the source system sent it — every header, the raw body — "
        "is handed to the connector that serves the channel. The connector verifies the "
        "signature before it reads the body, then normalises the event into the channel's "
        "half of a command. The identity component places the sender — the account must be "
        "linked to an identity — and the event is kept in that identity's tenant until it is "
        "completed into a command. A sender it cannot place is answered `unknown_sender` and "
        "nothing is kept; the sender is told in the channel how to link the account, or that "
        "a link code they wrote linked it. A verified delivery that is a handshake, not an "
        "event — a sender checking the address before it sends events — is refused with the "
        "answer the connector gives, and that answer is returned as it is, status 200; "
        "nothing is kept. Nothing is executed from here.",
        status_code=202,
        responses={
            200: {
                "description": "A handshake: the body and media type the connector answered "
                "for its sender, returned as they are.",
                "content": {"text/plain": {}, "application/json": {}},
            },
            202: {
                "description": "Decided: `accepted` with the intake event, `refused`, "
                "`unknown_sender` with whether the sender was answered in the channel and "
                "whether the message linked their account, or `answer` for a message in the "
                "thread of a report to the owner, with what became of it."
            },
            400: {"description": "The body cannot be read.", **PROBLEM},
            401: {"description": "Unsigned, or the signature does not verify.", **PROBLEM},
            404: {"description": "No connector serves the channel.", **PROBLEM},
            503: {"description": "The connector did not answer.", **PROBLEM},
            **INVALID,
        },
    )
    async def intake(channel: str, request: Request) -> Response:
        body = (await request.body()).decode("utf-8", errors="replace")
        delivery = Delivery(
            headers={k: v for k, v in request.headers.items()},
            body=body,
            received_at=datetime.now(UTC),
        )
        try:
            outcome = await services.intake.execute(
                # Where an event is kept is the identity component's to decide; the first
                # tenant is only where a sender nobody could place is answered from.
                ReceiveIntake(channel=channel, delivery=delivery, tenant=services.tenants[0])
            )
        except UnknownChannel as error:
            return problem(404, str(error))
        except ConnectorError as error:
            return problem(503, str(error))
        if outcome.refused is not None and outcome.refused.answer is not None:
            # A verified handshake: the connector knows what its sender expects back; the
            # surface copies it and knows no sender (ADR-0024, amendment of 2026-10-09).
            answer = outcome.refused.answer
            return Response(answer.body, status_code=200, media_type=answer.media_type)
        if outcome.refused is not None:
            status = REFUSAL_STATUS[outcome.refused.reason]
            if status == 202:
                return JSONResponse({"refused": outcome.refused.document()}, status_code=202)
            return problem(
                status,
                outcome.refused.detail,
                title="Refused",
                reason=outcome.refused.reason,
            )
        if outcome.answer is not None:
            # An answer to a report: taken by the owner-facing channel, kept as no event.
            return JSONResponse(
                {"answer": outcome.answer, "replied": outcome.replied}, status_code=202
            )
        if outcome.unknown_sender is not None:
            return JSONResponse(
                {
                    "unknown_sender": outcome.unknown_sender.document(),
                    "replied": outcome.replied,
                    "linked": outcome.linked is not None,
                },
                status_code=202,
            )
        if outcome.accepted is None:  # unreachable: an outcome is one of the three
            return problem(503, "the intake decided nothing")
        return JSONResponse({"accepted": outcome.accepted.document()}, status_code=202)

    tenant_query = Query(
        default=None,
        description="The tenant; the instance's first configured tenant when absent.",
    )

    @router.post(
        "/intake-events/{event_id}/complete",
        summary="Complete an intake event into a command",
        description="The event the connector accepted becomes a command: the identity component "
        "supplies who acts and the organisational path, from the link of the sender's account, "
        "and the event is marked completed. Nothing is executed; the command is returned for "
        "whoever commissions a plan from it.",
        status_code=200,
        responses={
            200: {"description": "The command the event became."},
            404: {"description": "No such intake event in the tenant.", **PROBLEM},
            409: {"description": "The event was completed before.", **PROBLEM},
            422: {"description": "The sender cannot be placed.", **PROBLEM},
        },
    )
    async def complete(event_id: str, tenant: str | None = tenant_query) -> JSONResponse:
        handler = services.complete_intake
        chosen = tenant or services.tenants[0]
        try:
            command = await handler.execute(CompleteIntake(tenant=chosen, event_id=event_id))
        except UnknownIntakeEvent as error:
            return problem(404, str(error))
        except AlreadyCompleted as error:
            return problem(409, str(error))
        except UnknownSender as error:
            return problem(422, str(error))
        return JSONResponse(command.document(), status_code=200)

    return router


class LinkCodeRequest(BaseModel):
    channel: str = Field(
        pattern=CAPABILITY_PATTERN,
        description="The channel whose account is to be linked, as a capability (`channel.repo`).",
    )


def _identity(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["identity"])

    @router.post(
        "/identity/link-codes",
        summary="Create a link code in your Taktus account",
        description="The account key in `Authorization: Bearer` proves the identity. The answer "
        "is a single-use code, valid for 30 minutes and shown once: written in the named "
        "channel from the account to be linked, it links that account to this identity. "
        "Nothing else links an account; a matching name or address never does (ADR-0040).",
        status_code=201,
        responses={
            201: {"description": "The code, the channel and when the code expires."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            **INVALID,
        },
    )
    async def create_link_code(
        request: LinkCodeRequest,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, "an account key is needed: Authorization: Bearer <key>")
        try:
            code, record = await services.identities.create_link_code(who, request.channel)
        except UnknownIdentity as error:
            return problem(401, str(error))
        return JSONResponse(
            {
                "code": code,
                "channel": record.channel,
                "identity": record.identity,
                "expires_at": record.expires_at.isoformat(),
            },
            status_code=201,
        )

    return router


async def _authenticated(services: RestServices, authorization: str | None) -> Resolution | None:
    """The identity the account key in `Authorization: Bearer` proves, or None."""
    scheme, _, key = (authorization or "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return await services.identities.authenticate(key.strip())


class AnswerBody(BaseModel):
    option: str | None = Field(
        default=None, pattern=r"^[A-Z]$", description="The identifier of one option."
    )
    text: str | None = Field(
        default=None, min_length=1, description="Free text, as you would write it."
    )


class ConfirmBody(BaseModel):
    confirmed: bool = Field(
        description="True: the reading sent back is right, and it takes effect. False: it is "
        "not; nothing takes effect and the request is open again."
    )


def _view(addressed: Addressed, reader: str) -> dict[str, Any]:
    """A request as a decider sees it. Who answered and when is shown to that person alone:
    the time it took is theirs (ADR-0015)."""
    request = addressed.request
    yours = request.answered_by == reader
    view: dict[str, Any] = {
        "id": request.id,
        "decider": request.decider,
        "anchor": request.anchor,
        "raised_at": request.raised_at.isoformat(),
        "overdue": addressed.overdue,
        "answered_by_you": yours,
        "request": request.request.document(),
    }
    if yours and request.reflection is not None:
        view["reflection"] = request.reflection
    return view


def _decisions(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["decisions"])
    unauthenticated: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM}
    }
    needs_key = "an account key is needed: Authorization: Bearer <key>"

    @router.get(
        "/decisions",
        summary="The decision requests addressed to you",
        description="Every request not yet applied whose deciding role your identity holds, "
        "the oldest due first; `overdue` marks one past its due date. Nothing waits silently "
        "(ADR-0042).",
        responses={200: {"description": "The requests."}, **unauthenticated, **INVALID},
    )
    async def addressed(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        waiting = await services.decision_queries.addressed_to(who.tenant, who.identity)
        return JSONResponse(
            {
                "identity": who.identity,
                "requests": [_view(a, who.identity) for a in waiting],
                "overdue": sum(1 for a in waiting if a.overdue),
            }
        )

    @router.get(
        "/decisions/response-times",
        summary="How long decisions took: yours, and the rest only aggregated",
        description="Your own response times, each decision with its time; everyone else's only "
        "aggregated by role and by department, never by person, and withheld where a group has "
        "fewer than two deciders (ADR-0015).",
        responses={
            200: {"description": "The response times you may read."},
            **unauthenticated,
            **INVALID,
        },
    )
    async def response_times(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        read = await services.decision_queries.response_times(who.tenant, who.identity)
        return JSONResponse(read.document())

    @router.get(
        "/decisions/{request_id}",
        summary="One decision request addressed to you",
        responses={
            200: {"description": "The request."},
            403: {"description": "The request is not addressed to you.", **PROBLEM},
            404: {"description": "No such request.", **PROBLEM},
            **unauthenticated,
            **INVALID,
        },
    )
    async def one(request_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        found = await services.decision_queries.one(who.tenant, request_id)
        if found is None:
            return problem(404, f"no decision request {request_id!r}")
        if found.request.decider not in who.roles:
            return problem(403, f"{request_id} is addressed to the role {found.request.decider}")
        return JSONResponse(_view(found, who.identity))

    @router.post(
        "/decisions/{request_id}/answer",
        summary="Answer a decision request",
        description="With `option`, one option by its identifier; with `text`, free text. "
        "Neither takes effect: the answer is read, the reading comes back in one message, and "
        "only once you confirm it does it take effect (ADR-0008). Free text from which no "
        "single option can be read changes nothing, and the message says so.",
        responses={
            200: {"description": "The message sent back, and the request."},
            403: {"description": "You do not hold the role that decides it.", **PROBLEM},
            404: {"description": "No such request.", **PROBLEM},
            409: {"description": "The request's answer already took effect.", **PROBLEM},
            **unauthenticated,
            **INVALID,
        },
    )
    async def answer(
        request_id: str, body: AnswerBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        try:
            answered = await services.answer_decision.execute(
                AnswerRequest(
                    tenant=who.tenant,
                    request_id=request_id,
                    identity=who.identity,
                    text=body.text,
                    option=body.option,
                )
            )
        except DecisionError as error:
            return _refused(error)
        found = Addressed(answered.request, overdue=False)
        return JSONResponse({"message": answered.message, "request": _view(found, who.identity)})

    @router.post(
        "/decisions/{request_id}/confirm",
        summary="Confirm, or reject, how your answer was read",
        description="Confirmed, the reading takes effect: the request is applied, the decision "
        "register gains its entry, and the run continues — or halts at its boundary, if the "
        "act was declined. Rejected, nothing takes effect and the request is open again.",
        responses={
            200: {"description": "Whether it was applied, and the register entry."},
            403: {"description": "You did not give the answer that was read.", **PROBLEM},
            404: {"description": "No such request.", **PROBLEM},
            409: {"description": "There is no reading to confirm.", **PROBLEM},
            **unauthenticated,
            **INVALID,
        },
    )
    async def confirm(
        request_id: str, body: ConfirmBody, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        try:
            confirmed = await services.confirm_decision.execute(
                ConfirmRequest(
                    tenant=who.tenant,
                    request_id=request_id,
                    identity=who.identity,
                    confirmed=body.confirmed,
                )
            )
        except DecisionError as error:
            return _refused(error)
        if confirmed.entry is not None:
            await services.decided(who.tenant, confirmed.entry.run_id, who.identity)
        return JSONResponse(
            {
                "applied": confirmed.entry is not None,
                "entry": None if confirmed.entry is None else confirmed.entry.id,
                "request": _view(Addressed(confirmed.request, overdue=False), who.identity),
            }
        )

    return router


def _owner(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["owner"])
    unauthenticated: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        403: {
            "description": "You are not the owner, nor someone the owner named.",
            **PROBLEM,
        },
    }
    needs_key = "an account key is needed: Authorization: Bearer <key>"
    not_a_reader = "only the owner, and the people the owner named, read the reports"

    @router.get(
        "/owner/reports",
        summary="What is needed from the owner",
        description="Every report to the owner — a decision request addressed to them, a need, "
        "a date, a failure Taktus noticed about itself — the open ones first, the earliest due "
        "first, each as its view: what is needed, the steps, what stands still, the date, every "
        "delivery with its outcome, and its history (ADR-0045). The history says whether you "
        "acted, never who did.",
        responses={200: {"description": "The reports."}, **unauthenticated, **INVALID},
    )
    async def reports(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        if not await services.owner_reports.may_read(who.tenant, who.identity):
            return problem(403, not_a_reader)
        found = await services.owner_reports.reports(who.tenant)
        return JSONResponse({"reports": [report_view(r, who.identity) for r in found]})

    @router.get(
        "/owner/reports/{report_id}",
        summary="One report to the owner, with its history",
        responses={
            200: {"description": "The report's view."},
            404: {"description": "No such report.", **PROBLEM},
            **unauthenticated,
            **INVALID,
        },
    )
    async def one(report_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        if not await services.owner_reports.may_read(who.tenant, who.identity):
            return problem(403, not_a_reader)
        found = await services.owner_reports.one(who.tenant, report_id)
        if found is None:
            return problem(404, f"no report {report_id!r}")
        return JSONResponse(report_view(found, who.identity))

    @router.get(
        "/owner/reports/{report_id}/text",
        summary="One report as a repository text",
        description="The report as a record in a repository: English, minimal — what future "
        "work needs, and where an answer was given, never what was said there.",
        responses={
            200: {"description": "The text.", "content": {"text/markdown": {}}},
            404: {"description": "No such report.", **PROBLEM},
            **unauthenticated,
            **INVALID,
        },
    )
    async def text(report_id: str, authorization: str | None = Header(default=None)) -> Any:
        who = await _authenticated(services, authorization)
        if who is None:
            return problem(401, needs_key)
        if not await services.owner_reports.may_read(who.tenant, who.identity):
            return problem(403, not_a_reader)
        found = await services.owner_reports.one(who.tenant, report_id)
        if found is None:
            return problem(404, f"no report {report_id!r}")
        return Response(repository_text(found), media_type="text/markdown")

    return router


def _refused(error: DecisionError) -> JSONResponse:
    if isinstance(error, UnknownRequest):
        return problem(404, str(error))
    if isinstance(error, NotTheDecider):
        return problem(403, str(error))
    if isinstance(error, NotAnswerable):
        return problem(409, str(error))
    return problem(422, str(error))


def _reads(services: RestServices) -> APIRouter:
    router = APIRouter(tags=["runs"])
    tenant_query = Query(
        default=None,
        description="The tenant; the instance's first configured tenant when absent.",
    )

    @router.get(
        "/runs",
        summary="The runs of a tenant, newest first",
        responses={
            200: {"description": "A list of runs as the run component records them."},
            **INVALID,
        },
    )
    async def list_runs(tenant: str | None = tenant_query) -> JSONResponse:
        chosen = tenant or services.tenants[0]
        async with services.work.transaction(chosen):
            runs = list(await services.runs.list(chosen))
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return JSONResponse({"tenant": chosen, "runs": [r.document() for r in runs]})

    @router.get(
        "/runs/{run_id}",
        summary="One run",
        responses={
            200: {"description": "The run."},
            404: {"description": "No such run in the tenant.", **PROBLEM},
            **INVALID,
        },
    )
    async def get_run(run_id: str, tenant: str | None = tenant_query) -> JSONResponse:
        chosen = tenant or services.tenants[0]
        async with services.work.transaction(chosen):
            run = await services.runs.get(chosen, run_id)
        if run is None:
            return problem(404, f"tenant {chosen!r} has no run {run_id!r}")
        return JSONResponse(run.document())

    @router.get(
        "/runs/{run_id}/ledger",
        summary="The ledger entries of one run, in sequence",
        responses={
            200: {"description": "The entries, and whether the tenant's chain verifies."},
            404: {"description": "No such run in the tenant.", **PROBLEM},
            **INVALID,
        },
    )
    async def run_ledger(run_id: str, tenant: str | None = tenant_query) -> JSONResponse:
        chosen = tenant or services.tenants[0]
        async with services.work.transaction(chosen):
            run = await services.runs.get(chosen, run_id)
            if run is None:
                return problem(404, f"tenant {chosen!r} has no run {run_id!r}")
            entries = await services.ledger.entries(chosen, run_id)
            verification = await services.ledger.verify(chosen)
        return JSONResponse(
            {
                "run_id": run_id,
                "entries": [e.document() for e in entries],
                "chain": {"intact": verification.intact, "entries": verification.entries},
            }
        )

    return router
