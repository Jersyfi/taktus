"""This instance's own findings and their review, on the HTTP surface (ADR-0122, UC-6.12).

`GET /findings` shows every product finding the instance recorded. Each comes with what the rule
over the release's list made of it (ADR-0118 §2), and exactly the words it would leave in. It is
read by the owner and the people the owner named, as the reports are.

At the level `review` a person answers each candidate in review as `taktusctl findings review`
does: `send`, `not` or `local`. The answer is read back first and changes nothing
(`POST /findings/{lack}/review`). Only its confirmation acts (`POST /findings/{lack}/review/
confirm`), and only on what was read back. The confirmation carries a digest of the reader, the
lack, the answer and the text. A text that changed in between is refused (ADR-0008).

The intake of other instances' findings is `findings.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.application.service import (
    NotACandidate,
    NotEnabled,
    Outgoing,
    ProductFindings,
)
from taktus.components.reporting.domain.service import texts
from taktus.ports.connector import ConnectorError
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]
type Answer = Literal["send", "not", "local"]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
NOT_A_READER = "only the owner, and the people the owner named, read the findings"
NONE_RECORDED = "this instance records no product findings"

READINGS: dict[str, str] = {
    "send": "You answer send: the text below leaves this instance now, exactly as shown.",
    "not": "You answer not now: nothing leaves, and it is offered again at the next review.",
    "local": "You answer local for us: nothing leaves, and this lack is never offered again.",
}
"""Each answer read back in words, before anything is done (ADR-0008)."""

KINDS: dict[str, str] = {
    "product": "a product candidate; it may leave, at the level the operator set",
    "configuration": "local, of configuration; a shipped adapter offers it once configured",
    "own": "local, of this project's own development; it never leaves",
    "local_for_us": "local for us; a person said so in review, and it never leaves",
}
"""What each kind means, in the words the page shows."""


class ReviewAnswer(BaseModel):
    """An answer to one candidate in review. A field the surface does not know is refused."""

    model_config = ConfigDict(extra="forbid")

    answer: Answer = Field(description="`send` it now, `not` now, or `local` for us.")


class ReviewConfirmation(BaseModel):
    """The reading of an answer, confirmed or rejected."""

    model_config = ConfigDict(extra="forbid")

    answer: Answer
    confirmation: str = Field(
        min_length=64,
        max_length=64,
        description="The `confirmation` the reading carried: a digest of what was read back.",
    )
    confirmed: bool = Field(description="True: do it. False: nothing is done.")


def finding_document(one: Outgoing, in_review: bool) -> dict[str, Any]:
    """One finding as the web app shows it: the lack, what it is, how often it was met, and the
    words it would leave in. The runs and steps are the instance's own, for its reader; what
    leaves names them by pseudonym. Nothing here names a person (principle 14)."""
    finding, lack = one.finding, one.finding.lack
    kind = "local_for_us" if one.local_for_us else one.classified.kind
    return {
        "lack": {"key": lack.key, "cause": lack.cause, "lacking": lack.lacking},
        "title": texts.title(lack),
        "kind": kind,
        "classified": {"kind": one.classified.kind, "adapters": list(one.classified.adapters)},
        "local_for_us": one.local_for_us,
        "leaves": one.leaves,
        "in_review": in_review,
        "occurrences": [
            {"run": o.run_id, "step": o.step_id, "since": o.since.isoformat(), "seconds": o.seconds}
            for o in finding.occurrences
        ],
        "waited_seconds": finding.waited,
        "text": one.text,
        "withheld": [{"kind": m.kind, "excerpt": m.excerpt} for m in one.withheld],
        "said": f"{texts.title(lack)}: {KINDS[kind]}.",
    }


def findings_summary(level: str, found: list[dict[str, Any]]) -> str:
    """One sentence: how many lacks, how many local, and what the operator's level does."""
    n = len(found)
    if n == 0:
        return "Nothing the product lacks was met here."
    waiting = sum(1 for f in found if f["in_review"])
    local = sum(1 for f in found if not f["leaves"])
    sentence = f"{n} {'lack' if n == 1 else 'lacks'} met, {local} of them kept here"
    if level == "review":
        sentence += f"; {waiting} {'waits' if waiting == 1 else 'wait'} for a review"
    elif level == "off":
        sentence += "; nothing leaves, because the operator's level is off"
    else:
        sentence += "; candidates leave on their own, because the operator's level is automatic"
    return sentence + "."


def findings_document(
    level: str, outgoing: Sequence[Outgoing], waiting: frozenset[str]
) -> dict[str, Any]:
    """The answer of `GET /findings`: the operator's level, the sentence, and every finding;
    `waiting` holds the keys of the lacks in review."""
    documents = [finding_document(o, o.finding.lack.key in waiting) for o in outgoing]
    return {
        "level": level,
        "summary": findings_summary(level, documents),
        "in_review": len(waiting),
        "findings": documents,
    }


def confirmation_of(identity: str, lack: str, answer: str, text: str) -> str:
    """The digest a confirmation must carry: of the reader, the lack, the answer and exactly the
    text that was read back. A text that changed since is a different digest."""
    material = "\n".join((identity, lack, answer, text)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["findings"])
    refused: dict[int | str, dict[str, Any]] = {
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        403: {"description": "You are not the owner, nor someone the owner named.", **PROBLEM},
        404: {"description": "This instance records no product findings.", **PROBLEM},
        422: {"description": "A parameter or the body does not validate.", **PROBLEM},
    }

    async def admitted(
        authorization: str | None,
    ) -> tuple[Resolution, ProductFindings] | JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if not await services.owner_reports.may_read(who.tenant, who.identity):
            return problem(403, NOT_A_READER)
        found = services.findings
        if found is None:
            return problem(404, NONE_RECORDED)
        return who, found

    async def in_review(found: ProductFindings, tenant: str, lack: str) -> Outgoing | None:
        return next((o for o in await found.pending(tenant) if o.finding.lack.key == lack), None)

    def not_in_review(found: ProductFindings, lack: str) -> JSONResponse:
        if found.level != "review":
            return problem(
                409, f"the operator's level is {found.level}: nobody reviews a finding here"
            )
        return problem(409, f"the lack {lack} is not in review: it is local, sent, or unknown")

    @routes.get(
        "/findings",
        summary="This instance's product findings, and what each one is",
        description="Every lack of the product this instance met, with what the rule over the "
        "release's list made of it — a product candidate, or local of configuration or of own "
        "development — how often it was met, how long it held runs up, and exactly the words "
        "it would leave in. `in_review` marks a candidate that waits for a person's answer at "
        "the level `review` (ADR-0118 §4). Read by the owner and whom the owner named. No "
        "field names a person.",
        responses={200: {"description": "The findings."}, **refused},
    )
    async def listed(authorization: str | None = Header(default=None)) -> JSONResponse:
        given = await admitted(authorization)
        if isinstance(given, JSONResponse):
            return given
        who, found = given
        waiting = frozenset(o.finding.lack.key for o in await found.pending(who.tenant))
        outgoing = await found.outgoing(who.tenant)
        return JSONResponse(findings_document(found.level, outgoing, waiting))

    @routes.post(
        "/findings/{lack}/review",
        summary="An answer to a candidate in review, read back",
        description="`send`, `not` or `local`, as `taktusctl findings review` takes it. Nothing "
        "is done: the answer comes back in words, with exactly the text that would leave and "
        "a `confirmation` to send with the confirmation (ADR-0008).",
        responses={
            200: {"description": "The reading, the text, and the confirmation to send."},
            **refused,
            409: {"description": "The lack is not in review.", **PROBLEM},
        },
    )
    async def review(
        lack: str, body: ReviewAnswer, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        given = await admitted(authorization)
        if isinstance(given, JSONResponse):
            return given
        who, found = given
        one = await in_review(found, who.tenant, lack)
        if one is None:
            return not_in_review(found, lack)
        return JSONResponse(
            {
                "lack": lack,
                "answer": body.answer,
                "reading": READINGS[body.answer],
                "text": one.text,
                "confirmation": confirmation_of(who.identity, lack, body.answer, one.text),
            }
        )

    @routes.post(
        "/findings/{lack}/review/confirm",
        summary="Confirm, or reject, the reading of an answer in review",
        description="Confirmed, the answer is done as it was read back: `send` sends what the "
        "other side has not been given of it, `local` remembers it as local for us, `not` "
        "does nothing. Rejected, nothing is done. A text that changed since it was read back "
        "is refused, and the answer is read back again.",
        responses={
            200: {"description": "What was done."},
            **refused,
            409: {
                "description": "Not in review, or what would leave changed since it was read back.",
                **PROBLEM,
            },
            502: {"description": "The way out did not take it.", **PROBLEM},
        },
    )
    async def confirm(
        lack: str, body: ReviewConfirmation, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        given = await admitted(authorization)
        if isinstance(given, JSONResponse):
            return given
        who, found = given
        if not body.confirmed:
            return JSONResponse(
                {"done": False, "answer": body.answer, "message": "Nothing was done."}
            )
        one = await in_review(found, who.tenant, lack)
        if one is None:
            return not_in_review(found, lack)
        if body.confirmation != confirmation_of(who.identity, lack, body.answer, one.text):
            return problem(
                409, "what would leave is not what was read back to you: read it back again"
            )
        try:
            if body.answer == "send":
                sent = await found.send_one(who.tenant, lack)
                message = (
                    "Not taken yet: the intake holds this sender until its owner confirms it."
                    if sent.held
                    else f"Sent: {sent.opened} opened, {sent.added} added."
                )
            elif body.answer == "local":
                await found.call_local(who.tenant, lack)
                message = "Remembered as local for us: it is never offered again."
            else:
                message = "Nothing was sent. It is offered again at the next review."
        except (NotEnabled, NotACandidate) as error:
            return problem(409, str(error))
        except ConnectorError as error:
            return problem(502, str(error), title="Bad gateway")
        return JSONResponse({"done": True, "answer": body.answer, "message": message})

    return routes
