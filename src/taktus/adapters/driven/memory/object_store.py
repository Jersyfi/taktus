from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from taktus.shared.v1 import Digest


class MemoryObjectStore:
    """Bytes by digest. With a directory, each object is also written to `<directory>/<hex>`."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._objects: dict[str, bytes] = {}

    async def put(self, content: bytes) -> Digest:
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        self._objects[digest] = content
        if self._directory is not None:
            path = self._directory / digest.removeprefix("sha256:")

            def _write() -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            await asyncio.to_thread(_write)
        return digest

    async def get(self, digest: Digest) -> bytes | None:
        if digest in self._objects:
            return self._objects[digest]
        if self._directory is not None:
            path = self._directory / digest.removeprefix("sha256:")
            if path.is_file():
                content = await asyncio.to_thread(path.read_bytes)
                self._objects[digest] = content
                return content
        return None
