"""The intake of findings from other instances on the HTTP surface (ADR-0118, UC-6.12).

`POST /findings/intake` takes one signed submission: a product finding's occurrence or a report
a person wrote by hand. It admits no account key and no other credential. The signature is the
only proof, and the intake checks it before it reads anything else. A new sender is held until
the owner of the intake's tenant confirms it once, in the owner's channel. Each sender is
rate-limited. Where the operator opened no intake, the route answers 404 and says how to open
it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from taktus.adapters.driving.rest.problems import problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.reporting.ports import Signed

PROBLEM: dict[str, Any] = {"content": {"application/problem+json": {}}}
NOT_OPEN = (
    "this instance takes no findings from other instances: its operator sets "
    "TAKTUS_FINDINGS_INTAKE_TENANT and TAKTUS_FINDINGS_CONNECTOR to open the intake"
)
STATUS = {
    "opened": 201,
    "added": 201,
    "known": 200,
    "held": 202,
    "forged": 401,
    "refused": 403,
    "invalid": 422,
    "limited": 429,
}
"""The status of each answer: taken, already known, held, or refused for a reason the sender
reads in the body."""
REFUSED = {
    "forged": "the signature does not verify under the key the submission names",
    "refused": "the key names a sender another key registered",
    "invalid": "the payload is not a submission, or it carries the shape of a personal datum",
    "limited": "over the sender's rate, or too many new senders wait for the owner",
}
"""Why each refusal was answered, for the sender's operator. A refusal is a problem, and its
`answer` says which."""


class Submitted(BaseModel):
    """One signed submission. A field the surface does not know is refused."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(
        min_length=1, max_length=200, description="The sender's public key, base64url."
    )
    payload: str = Field(
        min_length=1,
        max_length=40000,
        description="The submission as JSON text, exactly as it was signed.",
    )
    signature: str = Field(
        min_length=1, max_length=400, description="The signature over the payload, base64url."
    )


def router(services: RestServices) -> APIRouter:
    routes = APIRouter(tags=["findings"])

    @routes.post(
        "/findings/intake",
        summary="A finding or a report from another instance",
        description="One signed submission from a sending instance: a product finding's "
        "occurrence, closed values only, or a report a person wrote by hand. No credential is "
        "admitted; the signature over the payload is verified first. A sender's first "
        "submission registers its key and asks the owner of the intake's tenant to confirm it, "
        "in the owner's channel; until then every submission is `held`. A confirmed sender's "
        "finding opens the lack's issue in the repository, or adds an occurrence to the open "
        "one, through this instance's own connector.",
        responses={
            200: {"description": "`known`: the repository holds it already."},
            201: {"description": "`opened` or `added`: the issue was opened or added to."},
            202: {"description": "`held`: the sender waits for the owner's confirmation."},
            401: {"description": "`forged`: the signature does not verify.", **PROBLEM},
            403: {
                "description": "`refused`: the key names a sender another key registered.",
                **PROBLEM,
            },
            404: {"description": "The intake is not open on this instance.", **PROBLEM},
            422: {"description": "`invalid`: the payload is not a submission.", **PROBLEM},
            429: {
                "description": "`limited`: over the sender's rate, or too many new senders.",
                **PROBLEM,
            },
        },
    )
    async def intake(submitted: Submitted) -> JSONResponse:
        taken = services.findings_intake
        if taken is None:
            return problem(404, NOT_OPEN)
        received = await taken.receive(Signed.model_validate(submitted.model_dump()))
        if received.answer in REFUSED:
            return problem(
                STATUS[received.answer], REFUSED[received.answer], answer=received.answer
            )
        document: dict[str, Any] = {"answer": received.answer}
        if received.reference is not None:
            document["reference"] = received.reference
        return JSONResponse(document, status_code=STATUS[received.answer])

    return routes
