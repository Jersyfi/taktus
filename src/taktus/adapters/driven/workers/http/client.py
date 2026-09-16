"""One worker endpoint behind the worker port.

Every answer is validated against the contract's shapes before it reaches the core; an answer
that does not validate is a WorkerError naming the endpoint and the first violation, never a
half-read object. The stream is read until `assignment.finished`; a connection that drops is
reopened from the last sequence number seen (`Last-Event-ID`), which the contract obliges the
worker to honour (W-03). Two timeouts guard the read: `idle_timeout` between two events and
`stream_timeout` for the whole stream; either becomes a WorkerError, which the run engine treats
as a failed step.

Credential values never pass through here: the contract carries names, and the environment of
the worker process is the execution adapter's business.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import TypeAdapter, ValidationError

from taktus.ports.worker import (
    EVENT,
    ArtifactList,
    Assignment,
    AssignmentId,
    AssignmentState,
    Capabilities,
    Estimate,
    EstimateRequest,
    Event,
    StopRequest,
    WorkerError,
)
from taktus.shared.v1 import Artifact, Value
from taktus.wire.sse import messages


class HttpWorker:
    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 30.0,
        idle_timeout: float = 60.0,
        stream_timeout: float = 3600.0,
        reconnects: int = 3,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._idle_timeout = idle_timeout
        self._stream_timeout = stream_timeout
        self._reconnects = reconnects
        self._http = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=httpx.Timeout(timeout, connect=10.0),
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
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # --- the port ---------------------------------------------------------------------------

    async def capabilities(self) -> Capabilities:
        return await self._get("/v1/capabilities", Capabilities)

    async def estimate(self, request: EstimateRequest) -> Estimate:
        return await self._post("/v1/estimate", request, Estimate, expected=200)

    async def assign(self, assignment: Assignment) -> AssignmentState:
        return await self._post("/v1/assignments", assignment, AssignmentState, expected=201)

    async def state(self, assignment_id: AssignmentId) -> AssignmentState:
        return await self._get(f"/v1/assignments/{assignment_id}", AssignmentState)

    async def stop(self, assignment_id: AssignmentId, request: StopRequest) -> AssignmentState:
        return await self._post(
            f"/v1/assignments/{assignment_id}/stop", request, AssignmentState, expected=202
        )

    async def artifacts(self, assignment_id: AssignmentId) -> ArtifactList:
        return await self._get(f"/v1/assignments/{assignment_id}/artifacts", ArtifactList)

    async def artifact_bytes(self, assignment_id: AssignmentId, artifact: Artifact) -> bytes:
        uri = artifact.uri or f"/v1/assignments/{assignment_id}/artifacts/{artifact.id}"
        try:
            response = await self._http.get(uri, headers={"Accept": "*/*"})
        except httpx.HTTPError as error:
            raise WorkerError(f"{self.endpoint}: GET {uri} failed: {error!r}") from error
        if response.status_code != 200:
            raise WorkerError(f"{self.endpoint}: GET {uri} answered {response.status_code}")
        return response.content

    async def events(self, assignment_id: AssignmentId, *, after: int = 0) -> AsyncIterator[Event]:
        path = f"/v1/assignments/{assignment_id}/events"
        last_seq = after
        attempts = 0
        finished = False
        stream_timeout = httpx.Timeout(self._idle_timeout, connect=10.0)
        while not finished:
            headers = {"Accept": "text/event-stream"}
            if last_seq > 0:
                headers["Last-Event-ID"] = str(last_seq)
            try:
                async with self._http.stream(
                    "GET", path, headers=headers, timeout=stream_timeout
                ) as response:
                    if response.status_code != 200:
                        raise WorkerError(
                            f"{self.endpoint}: GET {path} answered {response.status_code}"
                        )
                    async for message in messages(response.aiter_lines()):
                        event = self._event(message.text, path)
                        if event.seq <= last_seq:
                            continue  # a replayed event after a reconnect
                        if event.seq != last_seq + 1:
                            raise WorkerError(
                                f"{self.endpoint}: {path} jumped from seq {last_seq} to {event.seq}"
                            )
                        last_seq = event.seq
                        yield event
                        if event.type == "assignment.finished":
                            finished = True
                            break
            except httpx.HTTPError as error:
                attempts += 1
                if attempts > self._reconnects:
                    raise WorkerError(
                        f"{self.endpoint}: the stream of {assignment_id} broke off after seq "
                        f"{last_seq} and did not come back: {error!r}"
                    ) from error
                continue
            if not finished:
                # The worker closed the stream without finishing: reconnect from where we were.
                attempts += 1
                if attempts > self._reconnects:
                    raise WorkerError(
                        f"{self.endpoint}: the stream of {assignment_id} ended after seq "
                        f"{last_seq} without assignment.finished"
                    )

    # --- plumbing ---------------------------------------------------------------------------

    def _event(self, text: str, path: str) -> Event:
        try:
            data = json.loads(text)
        except ValueError as error:
            raise WorkerError(f"{self.endpoint}: {path} sent data that is not JSON") from error
        try:
            return EVENT.validate_python(data)
        except ValidationError as error:
            raise WorkerError(f"{self.endpoint}: {path}: {_first(error)}") from error

    async def _get[T: Value](self, path: str, shape: type[T]) -> T:
        try:
            response = await self._http.get(path)
        except httpx.HTTPError as error:
            raise WorkerError(f"{self.endpoint}: GET {path} failed: {error!r}") from error
        return self._read(response, path, shape, expected=200)

    async def _post[T: Value](self, path: str, body: Value, shape: type[T], *, expected: int) -> T:
        try:
            response = await self._http.post(path, json=body.document())
        except httpx.HTTPError as error:
            raise WorkerError(f"{self.endpoint}: POST {path} failed: {error!r}") from error
        return self._read(response, path, shape, expected=expected)

    def _read[T: Value](
        self, response: httpx.Response, path: str, shape: type[T], *, expected: int
    ) -> T:
        if response.status_code != expected:
            detail = _problem(response)
            raise WorkerError(
                f"{self.endpoint}: {path} answered {response.status_code}"
                + (f": {detail}" if detail else "")
            )
        try:
            return TypeAdapter(shape).validate_json(response.content)
        except ValidationError as error:
            raise WorkerError(
                f"{self.endpoint}: {path} does not validate against {shape.__name__}: "
                f"{_first(error)}"
            ) from error


def _problem(response: httpx.Response) -> str:
    """The `detail` or `title` of an RFC 9457 problem, or nothing."""
    try:
        body: Any = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("title") or "")
    return ""


def _first(error: ValidationError) -> str:
    item = error.errors()[0]
    where = "/".join(str(p) for p in item["loc"]) or "<root>"
    return f"{where}: {item['msg']}"
