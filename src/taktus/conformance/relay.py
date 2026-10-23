"""The host side of the worker contract's outbound binding, as the suite serves it.

A worker in a network that admits no inbound connection connects to a host and fetches the
contract's requests from it (contracts/worker/v1/README.md §8, ADR-0139). Here the suite is that
host. It serves two paths under its base: `POST <base>/next` hands the worker the next request,
and `POST <base>/answers/{request_id}` takes the worker's answer, its body streamed while it
lasts. The suite's own client reaches the worker through `RelayTransport`, an HTTP transport
that turns each request into a relayed one and its answer back into a response. So every check
runs over the binding exactly as against an endpoint, and nothing in the suite knows the
difference.

The host records every request it relayed and every answer posted, in the `RelayProbe` shape
of Worker.json, which W-21 judges (`rules.relay_violations`). It needs no authentication: it
listens only where the suite is told to.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn

type Json = dict[str, Any]
type Scope = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
type Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

WAIT_SECONDS = 20.0
"""How long `/next` holds a poll without a request before it answers `204`; at most 30 (§8)."""
RELAYED_HEADERS = ("Accept", "Content-Type", "Last-Event-ID")


@dataclass
class _Pending:
    """One request on its way to the worker and its answer on its way back."""

    envelope: Json
    started: asyncio.Future[tuple[int, str]]
    chunks: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    abandoned: bool = False
    """The client stopped reading the answer: the rest of its body is not wanted."""


class RelayHost:
    """Serves the binding at `http://<host>:<port>/relay` while the suite runs."""

    def __init__(self, listen: str, *, wait_seconds: float = WAIT_SECONDS) -> None:
        host, _, port = listen.rpartition(":")
        if not host or not port.isdigit():
            raise ValueError(f"--listen takes host:port, not {listen!r}")
        self.host = host
        self.port = int(port)
        self.wait_seconds = wait_seconds
        self.base = f"http://{host}:{port}/relay"
        self.connected = asyncio.Event()
        self.relayed: list[Json] = []
        self.answers: list[Json] = []
        self._queue: asyncio.Queue[_Pending] = asyncio.Queue()
        self._open: dict[str, _Pending] = {}
        self._closing = asyncio.Event()
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    # --- lifetime --------------------------------------------------------------------------

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="warning",
            lifespan="off",
            interface="asgi3",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            if self._task.done():
                self._task.result()  # raises what stopped the server, such as a taken port
                raise RuntimeError(f"the relay host on {self.base} did not start")
            await asyncio.sleep(0.02)

    async def close(self) -> None:
        """Answers every waiting `/next` at once, so that the server stops without waiting for
        the worker's polls to time out."""
        self._closing.set()
        for pending in self._open.values():
            if not pending.started.done():
                pending.started.set_exception(httpx.ConnectError("the relay host closed"))
            pending.chunks.put_nowait(None)
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def transport(self) -> RelayTransport:
        return RelayTransport(self)

    def probe(self) -> Json:
        """What W-21 judges, in the shape `RelayProbe` of Worker.json."""
        return {"relayed": list(self.relayed), "answers": list(self.answers)}

    # --- the two paths -----------------------------------------------------------------------

    async def _app(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path: str = scope["path"]
        if scope["method"] == "POST" and path == "/relay/next":
            await self._drain(receive)
            await self._next(send)
        elif scope["method"] == "POST" and path.startswith("/relay/answers/"):
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            await self._answer(path.removeprefix("/relay/answers/"), headers, receive, send)
        else:
            await _respond(send, 404, {"title": "no such path of the binding", "status": 404})

    async def _next(self, send: Send) -> None:
        self.connected.set()
        taking = asyncio.ensure_future(self._queue.get())
        closing = asyncio.ensure_future(self._closing.wait())
        done, _ = await asyncio.wait(
            (taking, closing), timeout=self.wait_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        closing.cancel()
        if taking not in done:
            taking.cancel()
            await _respond(send, 204, None)
            return
        pending = taking.result()
        self._open[pending.envelope["request_id"]] = pending
        self.relayed.append(pending.envelope)
        await _respond(send, 200, pending.envelope)

    async def _answer(
        self, request_id: str, headers: dict[str, str], receive: Receive, send: Send
    ) -> None:
        raw = headers.get("relay-status", "")
        status = int(raw) if raw.isdigit() else None
        self.answers.append({"request_id": request_id, "status": status})
        pending = self._open.pop(request_id, None)
        if pending is None:
            await self._drain(receive)
            known = any(r["request_id"] == request_id for r in self.relayed)
            title = "answered already" if known else "no request of this id was relayed"
            code = 409 if known else 404
            await _respond(send, code, {"title": title, "status": code})
            return
        if status is None or not 100 <= status <= 599:
            await self._drain(receive)
            pending.started.set_exception(
                httpx.RemoteProtocolError(f"the answer to {request_id} carries no Relay-Status")
            )
            await _respond(send, 400, {"title": "no status in Relay-Status", "status": 400})
            return
        pending.started.set_result((status, headers.get("content-type", "")))
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            body: bytes = message.get("body", b"")
            if body and not pending.abandoned:
                pending.chunks.put_nowait(body)
            if pending.abandoned or not message.get("more_body", False):
                break
        pending.chunks.put_nowait(None)
        await _respond(send, 204, None)

    @staticmethod
    async def _drain(receive: Receive) -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect" or not message.get("more_body", False):
                return

    # --- the client side ---------------------------------------------------------------------

    async def relay(self, request: httpx.Request) -> _Pending:
        content = await request.aread()
        envelope: Json = {
            "request_id": "rly_" + secrets.token_hex(8),
            "method": request.method,
            "path": request.url.raw_path.decode(),
        }
        headers = {h: request.headers[h] for h in RELAYED_HEADERS if h in request.headers}
        if headers:
            envelope["headers"] = headers
        if content:
            envelope["body"] = content.decode()
        pending = _Pending(envelope, asyncio.get_running_loop().create_future())
        await self._queue.put(pending)
        return pending


class RelayTransport(httpx.AsyncBaseTransport):
    """An HTTP transport whose every request is relayed to the connected worker."""

    def __init__(self, host: RelayHost) -> None:
        self._host = host

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        timeouts = request.extensions.get("timeout") or {}
        read = timeouts.get("read") or 60.0
        pending = await self._host.relay(request)
        try:
            status, content_type = await asyncio.wait_for(pending.started, read)
        except TimeoutError as error:
            raise httpx.ReadTimeout(
                f"no worker answered {request.method} {request.url.path} within {read:.0f}s "
                "over the outbound binding",
                request=request,
            ) from error
        headers = [("content-type", content_type)] if content_type else []
        return httpx.Response(
            status, headers=headers, stream=_Answer(pending, read, request), request=request
        )


class _Answer(httpx.AsyncByteStream):
    def __init__(self, pending: _Pending, read: float, request: httpx.Request) -> None:
        self._pending = pending
        self._read = read
        self._request = request

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            try:
                chunk = await asyncio.wait_for(self._pending.chunks.get(), self._read)
            except TimeoutError as error:
                raise httpx.ReadTimeout(
                    "the answer over the outbound binding fell silent", request=self._request
                ) from error
            if chunk is None:
                return
            yield chunk

    async def aclose(self) -> None:
        self._pending.abandoned = True


async def _respond(send: Send, status: int, body: Json | None) -> None:
    data = b"" if body is None else json.dumps(body).encode()
    headers = [(b"content-length", str(len(data)).encode())]
    if body is not None:
        content_type = b"application/problem+json" if status >= 400 else b"application/json"
        headers.append((b"content-type", content_type))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})
