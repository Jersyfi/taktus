"""The host of the worker contract's outbound binding, on the `api` role (ADR-0156 §3, #625).

A worker in a network that admits no inbound connection connects to any instance and fetches
its requests from here (contracts/worker/v1 §8). Its base is `<prefix>/workers/<name>/relay`:

- `POST /workers/{name}/relay/next` — the next request for the worker, `200` with a
  `RelayRequest`, or `204` when none arrived within the wait;
- `POST /workers/{name}/relay/answers/{request_id}` — the answer to one: `Relay-Status` its
  status, `Content-Type` its type, the body as it is streamed. `204` once it ended; `404` for a
  request of no such worker or none; `409` for one answered already.

Both need `Authorization: Bearer <connect key>`, the key the instance is configured with for
that worker, compared in constant time. Without it, or with another, the answer is `401` and
nothing is taken or written. A worker that is not configured as connected, or has no key, is
`404`. The requests come from the relay every instance shares, so a worker connected to this
instance serves the runners of every instance.
"""

from __future__ import annotations

import asyncio
import hmac
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.ports.configuration import Secret
from taktus.ports.relay import Relay

WAIT_SECONDS = 20.0
"""How long `/next` waits for a request before it answers `204`; at most 30 (§8)."""
POLL_SECONDS = 0.05
PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}


@dataclass(frozen=True)
class ConnectedHost:
    """What the host needs: the relay, and the connect key of every connected worker by its
    name — the last segment of its adapter identifier."""

    relay: Relay
    keys: Mapping[str, Secret]
    wait_seconds: float = WAIT_SECONDS
    poll_seconds: float = POLL_SECONDS


def router(host: ConnectedHost | None) -> APIRouter:
    routes = APIRouter(tags=["workers"])
    common: dict[int | str, dict[str, Any]] = {
        401: {"description": "No connect key, or not the worker's.", **PROBLEM},
        404: {"description": "No worker of this name connects to the instance.", **PROBLEM},
    }

    def admitted(name: str, authorization: str | None) -> JSONResponse | None:
        """None when the caller presents the worker's key; the refusal otherwise."""
        key = None if host is None else host.keys.get(name)
        if key is None:
            return problem(404, f"no worker {name!r} connects to this instance")
        scheme, _, presented = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            presented.strip().encode(), key.reveal().encode()
        ):
            return problem(401, "the worker's connect key is needed: Authorization: Bearer <key>")
        return None

    @routes.post(
        "/workers/{name}/relay/next",
        summary="The next request for a connected worker",
        description="A worker that connects outbound fetches the next request of the worker "
        "contract here. Answered `200` with a `RelayRequest` of contracts/worker/v1, or `204` "
        "when none arrived within the wait (ADR-0156).",
        responses={
            200: {"description": "The request."},
            204: {"description": "None yet."},
            **common,
        },
    )
    async def next_request(
        name: str, authorization: str | None = Header(default=None)
    ) -> Response:
        refused = admitted(name, authorization)
        if refused is not None or host is None:
            return refused or problem(404, f"no worker {name!r} connects to this instance")
        worker = f"worker.{name}"
        deadline = time.monotonic() + host.wait_seconds
        while True:
            taken = await host.relay.take(worker)
            if taken is not None:
                return JSONResponse(taken.document())
            if time.monotonic() >= deadline:
                return Response(status_code=204)
            await asyncio.sleep(host.poll_seconds)

    @routes.post(
        "/workers/{name}/relay/answers/{request_id}",
        summary="The answer of a connected worker to one request",
        description="The header `Relay-Status` carries the answer's status, `Content-Type` its "
        "type, and the body is the answer's body, streamed while it lasts (ADR-0156).",
        responses={
            204: {"description": "Received."},
            409: {"description": "Answered already.", **PROBLEM},
            **common,
        },
    )
    async def answer(
        name: str,
        request_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
        relay_status: str | None = Header(default=None),
        content_type: str | None = Header(default=None),
    ) -> Response:
        refused = admitted(name, authorization)
        if refused is not None or host is None:
            return refused or problem(404, f"no worker {name!r} connects to this instance")
        status = int(relay_status) if relay_status and relay_status.isdigit() else None
        if status is None or not 100 <= status <= 599:
            return problem(400, "Relay-Status carries the answer's status code")
        begun = await host.relay.begin(f"worker.{name}", request_id, status, content_type)
        if begun == "unknown":
            return problem(404, f"no request {request_id!r} was relayed to this worker")
        if begun == "answered":
            return problem(409, f"the request {request_id!r} was answered already")
        seq = 0
        async for chunk in request.stream():
            if not chunk:
                continue
            seq += 1
            if not await host.relay.append(request_id, seq, chunk):
                break  # nobody reads the answer any more
        await host.relay.end(request_id)
        return Response(status_code=204)

    return routes
