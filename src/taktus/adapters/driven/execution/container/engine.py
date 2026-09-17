"""The container engine's HTTP API over its socket: what the container adapter needs of it.

The engine is whatever answers the Docker Engine API on the socket — Docker or Podman
(ADR-0002). No command-line client is needed, so the control plane image needs none. Every
call here is one endpoint of that API; the adapter composes them. Errors carry the engine's
own message, which names images and containers and never a secret.
"""

from __future__ import annotations

import asyncio
import io
import tarfile
from types import TracebackType
from typing import Any, Self

import httpx

from taktus.ports.execution import ExecutionError

type Json = dict[str, Any]


class EngineError(ExecutionError):
    """The engine refused or failed a call."""


class Engine:
    def __init__(self, socket: str, *, timeout: float = 60.0) -> None:
        self._http = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=socket),
            base_url="http://engine",
            timeout=httpx.Timeout(timeout, connect=5.0),
        )
        self.socket = socket

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

    # --- images -------------------------------------------------------------------------------

    async def image(self, reference: str) -> Json | None:
        response = await self._request("GET", f"/images/{reference}/json", ok=(200, 404))
        return None if response.status_code == 404 else self._json(response)

    async def pull(self, reference: str) -> None:
        name, _, tag = reference.rpartition(":")
        if not name or "/" in tag:
            name, tag = reference, "latest"
        async with self._http.stream(
            "POST", "/images/create", params={"fromImage": name, "tag": tag}, timeout=600.0
        ) as response:
            if response.status_code != 200:
                raise EngineError(
                    f"pulling {reference} failed: {(await response.aread()).decode()[:200]}"
                )
            async for line in response.aiter_lines():
                if '"error"' in line:
                    raise EngineError(f"pulling {reference} failed: {line[:200]}")

    async def ensure_image(self, reference: str) -> Json:
        found = await self.image(reference)
        if found is None:
            await self.pull(reference)
            found = await self.image(reference)
        if found is None:
            raise EngineError(f"image {reference} is not available after pulling it")
        return found

    # --- networks -----------------------------------------------------------------------------

    async def create_network(self, name: str, *, internal: bool) -> str:
        response = await self._request(
            "POST",
            "/networks/create",
            json={"Name": name, "Driver": "bridge", "Internal": internal, "CheckDuplicate": True},
        )
        return str(self._json(response)["Id"])

    async def connect(self, network: str, container: str) -> None:
        await self._request("POST", f"/networks/{network}/connect", json={"Container": container})

    async def remove_network(self, network: str) -> None:
        await self._request("DELETE", f"/networks/{network}", ok=(204, 404))

    # --- containers ---------------------------------------------------------------------------

    async def create_container(self, name: str, config: Json) -> str:
        response = await self._request(
            "POST", "/containers/create", params={"name": name}, json=config
        )
        return str(self._json(response)["Id"])

    async def start(self, container: str) -> None:
        await self._request("POST", f"/containers/{container}/start", ok=(204, 304))

    async def inspect(self, container: str) -> Json | None:
        response = await self._request("GET", f"/containers/{container}/json", ok=(200, 404))
        return None if response.status_code == 404 else self._json(response)

    async def kill(self, container: str, signal: str = "SIGKILL") -> None:
        await self._request(
            "POST", f"/containers/{container}/kill", params={"signal": signal}, ok=(204, 404, 409)
        )

    async def remove(self, container: str) -> None:
        await self._request(
            "DELETE", f"/containers/{container}", params={"force": "true"}, ok=(204, 404)
        )

    async def put_file(self, container: str, path: str, content: bytes, *, mode: int) -> None:
        """One file into the container's filesystem at `path`, through the archive endpoint —
        the engine's `cp`. Not into a tmpfs, which the endpoint cannot reach."""
        relative = path.lstrip("/")
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            parts = relative.split("/")[:-1]
            for depth in range(1, len(parts) + 1):  # the directories above it, world-readable
                directory = tarfile.TarInfo("/".join(parts[:depth]))
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o755
                archive.addfile(directory)
            info = tarfile.TarInfo(relative)
            info.size = len(content)
            info.mode = mode
            archive.addfile(info, io.BytesIO(content))
        await self._request(
            "PUT",
            f"/containers/{container}/archive",
            params={"path": "/"},
            content=buffer.getvalue(),
            headers={"Content-Type": "application/x-tar"},
        )

    async def exec(self, container: str, command: list[str], *, env: list[str]) -> int:
        """Run a command inside the container as its user and wait for it; the exit code.
        `env` reaches the command's environment only — it is not part of the container's
        recorded configuration."""
        created = await self._request(
            "POST",
            f"/containers/{container}/exec",
            json={"Cmd": command, "Env": env, "AttachStdout": False, "AttachStderr": False},
        )
        exec_id = str(self._json(created)["Id"])
        await self._request("POST", f"/exec/{exec_id}/start", json={"Detach": True})
        for _ in range(600):
            state = self._json(await self._request("GET", f"/exec/{exec_id}/json"))
            if not state.get("Running"):
                return int(state.get("ExitCode") or 0)
            await asyncio.sleep(0.05)
        raise EngineError(f"the command {command[0]!r} in {container} did not finish")

    async def logs(self, container: str) -> bytes:
        """stdout and stderr of the container so far, demultiplexed."""
        response = await self._request(
            "GET",
            f"/containers/{container}/logs",
            params={"stdout": "true", "stderr": "true"},
            ok=(200, 404),
        )
        if response.status_code == 404:
            return b""
        return demultiplex(response.content)

    # --- plumbing -----------------------------------------------------------------------------

    async def _request(
        self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201, 204), **more: Any
    ) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **more)
        except httpx.HTTPError as error:
            raise EngineError(
                f"the container engine at {self.socket} did not answer {method} {path}: {error!r}"
            ) from error
        if response.status_code not in ok:
            detail = ""
            try:
                detail = str(response.json().get("message", ""))
            except ValueError:
                detail = response.text[:200]
            raise EngineError(f"{method} {path} answered {response.status_code}: {detail}")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Json:
        # The engine's answers are objects; what they hold is the engine's business.
        result: Json = response.json()
        return result


def demultiplex(raw: bytes) -> bytes:
    """The engine's log stream: 8-byte frames (stream type, three zero bytes, big-endian
    length) around each chunk when the container has no TTY."""
    out = bytearray()
    offset = 0
    while offset + 8 <= len(raw):
        if raw[offset] not in (0, 1, 2) or raw[offset + 1 : offset + 4] != b"\x00\x00\x00":
            return raw  # a TTY stream is not framed
        length = int.from_bytes(raw[offset + 4 : offset + 8], "big")
        offset += 8
        out += raw[offset : offset + length]
        offset += length
    return bytes(out)


def config_of(image: Json) -> tuple[list[str], list[str]]:
    """The entrypoint and command an image would run as it is."""
    config = image.get("Config") or {}
    return list(config.get("Entrypoint") or []), list(config.get("Cmd") or [])
