"""The HTTP and SSE side of the suite: how it talks to a worker.

Nothing here knows what the checks mean. It posts bodies, reads streams and returns what came
back — status codes, parsed JSON, raw text — so that the suite can judge it. A worker written in
any language sees exactly what a foreign control plane would send.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import httpx

from taktus.wire.sse import Message, messages

type Json = dict[str, Any]


@dataclass
class Response:
    status: int
    text: str
    body: Any = None

    @property
    def json(self) -> Json | None:
        return self.body if isinstance(self.body, dict) else None


@dataclass
class Stream:
    """What one GET /events returned: every SSE message, the events parsed from them, and every
    problem with the transport itself (a non-200 answer, a message that is not JSON)."""

    status: int
    messages: list[Message] = field(default_factory=list)
    events: list[Json] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    timed_out: bool = False

    @property
    def raw(self) -> list[str]:
        return [m.text for m in self.messages]


class WorkerClient:
    def __init__(self, endpoint: str, *, timeout: float, idle_timeout: float) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self._http = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=httpx.Timeout(idle_timeout, connect=10.0),
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def get(self, path: str) -> Response:
        response = await self._http.get(path)
        return self._wrap(response)

    async def post(self, path: str, body: Json | None = None) -> Response:
        response = await self._http.post(path, json=body)
        return self._wrap(response)

    async def get_bytes(self, uri: str) -> tuple[int, bytes]:
        """Bytes at a URI: relative to the worker, or absolute http(s)."""
        response = await self._http.get(uri, headers={"Accept": "*/*"})
        return response.status_code, response.content

    @staticmethod
    def _wrap(response: httpx.Response) -> Response:
        text = response.text
        body: Any = None
        if text:
            try:
                body = json.loads(text)
            except ValueError:
                body = None
        return Response(response.status_code, text, body)

    async def stream(
        self,
        assignment_id: str,
        *,
        after: int | None = None,
        last_event_id: int | None = None,
        on_event: Callable[[Json], Coroutine[Any, Any, None]] | None = None,
    ) -> Stream:
        """Read the event stream until assignment.finished, or until the worker closes the
        connection. `on_event` runs for every parsed event while the stream is open — this is
        how a stop is requested mid-run."""
        params = {} if after is None else {"after": str(after)}
        headers = {"Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        result = Stream(status=0)
        try:
            async with asyncio.timeout(self.timeout):
                async with self._http.stream(
                    "GET", f"/v1/assignments/{assignment_id}/events", params=params, headers=headers
                ) as response:
                    result.status = response.status_code
                    if response.status_code != 200:
                        await response.aread()
                        result.problems.append(
                            f"GET /v1/assignments/{assignment_id}/events answered "
                            f"{response.status_code}: {response.text[:200]}"
                        )
                        return result
                    async for message in messages(response.aiter_lines()):
                        result.messages.append(message)
                        try:
                            event = json.loads(message.text)
                        except ValueError:
                            result.problems.append(
                                f"SSE message id={message.id!r} carries data that is not JSON"
                            )
                            continue
                        if not isinstance(event, dict):
                            result.problems.append(
                                f"SSE message id={message.id!r} carries JSON that is not an object"
                            )
                            continue
                        result.events.append(event)
                        if on_event is not None:
                            await on_event(event)
                        if event.get("type") == "assignment.finished":
                            break
        except TimeoutError:
            result.timed_out = True
            result.problems.append(
                f"the stream of {assignment_id} did not end within {self.timeout:.0f}s"
            )
        except httpx.HTTPError as error:
            result.problems.append(f"reading the stream of {assignment_id} failed: {error!r}")
        return result
