"""A worker connected outbound, behind the worker port (ADR-0156 §2).

The worker opens no port. It polls a host of the outbound binding on any instance, and the
requests it is given wait in the relay every instance shares (`ports/relay.py`). So this side is
the same HTTP client as for a worker at an endpoint, given a transport that writes each request
into the relay and reads its answer back from there as it arrives: the head first, then the body
chunk by chunk. The stream of events is therefore read as at an endpoint, reconnect from
`Last-Event-ID` included, and a restart of the host the worker was connected to is a stream
that fell silent, which the client already handles.

A request whose answer did not begin within the read timeout fails as a read timeout. A request
read to its end, or no longer read, is done and removed from the relay — unless the transport
keeps it, which the instance's conformance suite does until it has read what W-21 judges.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import AsyncIterator

import httpx

from taktus.adapters.driven.workers.http.client import HttpWorker
from taktus.ports.relay import Relay
from taktus.ports.worker import RelayRequest

POLL_SECONDS = 0.05
"""How often the relay is read for an answer and its chunks (ADR-0156, *Where this promise
ends*)."""
RELAYED_HEADERS = ("Accept", "Content-Type", "Last-Event-ID")
BASE = "http://connected.relay"
"""The address the client is given: a label, never reached over the network."""


class RelayTransport(httpx.AsyncBaseTransport):
    """An HTTP transport whose every request is relayed to one connected worker."""

    def __init__(
        self, relay: Relay, worker: str, *, keep: bool = False, poll: float = POLL_SECONDS
    ) -> None:
        self._relay = relay
        self._worker = worker
        self._keep = keep
        self._poll = poll
        self.relayed: list[RelayRequest] = []
        """Every request relayed, in order: what the conformance suite's W-21 judges."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        timeouts = request.extensions.get("timeout") or {}
        read = float(timeouts.get("read") or 60.0)
        content = await request.aread()
        headers = {h: request.headers[h] for h in RELAYED_HEADERS if h in request.headers}
        if request.method not in ("GET", "POST"):
            raise httpx.UnsupportedProtocol(
                f"the binding relays GET and POST, not {request.method}"
            )
        envelope = RelayRequest.model_validate(
            {
                "request_id": "rly_" + secrets.token_hex(8),
                "method": request.method,
                "path": request.url.raw_path.decode(),
                **({"headers": headers} if headers else {}),
                **({"body": content.decode()} if content else {}),
            }
        )
        await self._relay.put(self._worker, envelope)
        self.relayed.append(envelope)
        deadline = time.monotonic() + read
        while (head := await self._relay.answer(envelope.request_id)) is None:
            if time.monotonic() > deadline:
                await self.done(envelope.request_id)
                raise httpx.ReadTimeout(
                    f"no worker answered {request.method} {request.url.path} within {read:.0f}s "
                    "over the outbound binding",
                    request=request,
                )
            await asyncio.sleep(self._poll)
        answer_headers = [("content-type", head.content_type)] if head.content_type else []
        return httpx.Response(
            head.status,
            headers=answer_headers,
            stream=_Answer(self, envelope.request_id, read, request),
            request=request,
        )

    async def done(self, request_id: str) -> None:
        if not self._keep:
            await self._relay.done(request_id)

    async def forget(self) -> None:
        """Remove every request this transport relayed: the end of a conformance run."""
        for envelope in self.relayed:
            await self._relay.done(envelope.request_id)

    @property
    def relay(self) -> Relay:
        return self._relay

    @property
    def poll(self) -> float:
        return self._poll


class _Answer(httpx.AsyncByteStream):
    def __init__(
        self, transport: RelayTransport, request_id: str, read: float, request: httpx.Request
    ) -> None:
        self._transport = transport
        self._id = request_id
        self._read = read
        self._request = request
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        relay, after = self._transport.relay, 0
        quiet_since = time.monotonic()
        while True:
            found = await relay.chunks(self._id, after)
            for seq, chunk in found.chunks:
                after = seq
                quiet_since = time.monotonic()
                yield chunk
            if found.ended or found.gone:
                return
            if time.monotonic() - quiet_since > self._read:
                raise httpx.ReadTimeout(
                    "the answer over the outbound binding fell silent", request=self._request
                )
            await asyncio.sleep(self._transport.poll)

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._transport.done(self._id)


def connected_worker(
    relay: Relay,
    adapter: str,
    *,
    keep: bool = False,
    timeout: float = 30.0,
    idle_timeout: float = 60.0,
    stream_timeout: float = 3600.0,
) -> HttpWorker:
    """The worker port over the relay, for the connected worker `adapter` names."""
    return HttpWorker(
        BASE,
        timeout=timeout,
        idle_timeout=idle_timeout,
        stream_timeout=stream_timeout,
        transport=RelayTransport(relay, adapter, keep=keep),
    )
