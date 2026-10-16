"""The object store in memory, for development and tests."""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from pathlib import Path

from taktus.shared.v1 import Digest

DEFAULT_CACHE_BYTES = 64 * 1024 * 1024
"""How many bytes of objects a store with a directory keeps in memory unless told otherwise:
64 MiB, a sixth of the smallest memory limit the chart gives a role (#311)."""


class MemoryObjectStore:
    """Bytes by digest.

    Without a directory, memory is the only place an object lives, and the store keeps every
    object it was given. With a directory, each object is written to `<directory>/<hex>`, and
    the directory is where it lives. Memory then holds a cache of at most `cache_bytes` bytes:
    the objects read or written most recently. The least recently used object leaves the cache
    first, and an object larger than the whole cache is never cached. `cache_bytes=0` caches
    nothing. An object that left the cache is read again from the directory.
    """

    def __init__(
        self, directory: Path | None = None, *, cache_bytes: int = DEFAULT_CACHE_BYTES
    ) -> None:
        if cache_bytes < 0:
            raise ValueError("cache_bytes must not be negative")
        self._directory = directory
        self._limit = cache_bytes
        self._objects: OrderedDict[str, bytes] = OrderedDict()
        self._cached = 0

    @property
    def cached_bytes(self) -> int:
        """How many bytes of objects memory holds now."""
        return self._cached

    def _keep(self, digest: str, content: bytes) -> None:
        if self._directory is None:
            if digest not in self._objects:
                self._objects[digest] = content
                self._cached += len(content)
            return
        if digest in self._objects:
            self._objects.move_to_end(digest)
            return
        if len(content) > self._limit:
            return
        self._objects[digest] = content
        self._cached += len(content)
        while self._cached > self._limit:
            _, evicted = self._objects.popitem(last=False)
            self._cached -= len(evicted)

    async def put(self, content: bytes) -> Digest:
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if self._directory is not None:
            path = self._directory / digest.removeprefix("sha256:")

            def _write() -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            await asyncio.to_thread(_write)
        self._keep(digest, content)
        return digest

    async def get(self, digest: Digest) -> bytes | None:
        if digest in self._objects:
            if self._directory is not None:
                self._objects.move_to_end(digest)
            return self._objects[digest]
        if self._directory is not None:
            path = self._directory / digest.removeprefix("sha256:")
            if path.is_file():
                content = await asyncio.to_thread(path.read_bytes)
                self._keep(digest, content)
                return content
        return None
