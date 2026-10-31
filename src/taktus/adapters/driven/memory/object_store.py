"""The object store in memory or in a directory: the default adapter (ADR-0002, ADR-0165)."""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict
from pathlib import Path

import structlog

from taktus.ports.objectstore import ObjectStoreUnavailable
from taktus.shared.v1 import Digest

DEFAULT_CACHE_BYTES = 64 * 1024 * 1024
"""How many bytes of objects a store with a directory keeps in memory unless told otherwise:
64 MiB, a sixth of the smallest memory limit the chart gives a role (#311)."""

_log = structlog.get_logger("taktus.objects")


def digest_of(content: bytes) -> Digest:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def verified(digest: Digest, content: bytes, *, where: str) -> bytes | None:
    """The bytes when they hash to their name; None, logged, when they do not: other bytes
    than were written never reach a step as content (ADR-0165 §2)."""
    if digest_of(content) == digest:
        return content
    _log.warning("object_store.digest_mismatch", digest=digest, where=where)
    return None


class ObjectCache:
    """The objects read or written most recently, at most `limit` bytes of them. The least
    recently used leaves first; an object larger than the whole cache is never kept; a limit
    of 0 keeps nothing (#311)."""

    def __init__(self, limit: int) -> None:
        if limit < 0:
            raise ValueError("cache_bytes must not be negative")
        self._limit = limit
        self._objects: OrderedDict[str, bytes] = OrderedDict()
        self.size = 0

    def get(self, digest: str) -> bytes | None:
        content = self._objects.get(digest)
        if content is not None:
            self._objects.move_to_end(digest)
        return content

    def keep(self, digest: str, content: bytes) -> None:
        if digest in self._objects:
            self._objects.move_to_end(digest)
            return
        if len(content) > self._limit:
            return
        self._objects[digest] = content
        self.size += len(content)
        while self.size > self._limit:
            _, evicted = self._objects.popitem(last=False)
            self.size -= len(evicted)


class MemoryObjectStore:
    """Bytes by digest.

    Without a directory, memory is the only place an object lives, and the store keeps every
    object it was given. With a directory — the adapter `filesystem` — each object is written
    to `<directory>/<hex>`, and the directory is where it lives. Memory then holds a cache of
    at most `cache_bytes` bytes (`ObjectCache`). An object that left the cache is read again
    from the directory, and its bytes are checked against its name. A directory that cannot
    be written or read raises `ObjectStoreUnavailable`.
    """

    def __init__(
        self, directory: Path | None = None, *, cache_bytes: int = DEFAULT_CACHE_BYTES
    ) -> None:
        self._directory = directory
        self._cache = ObjectCache(cache_bytes)
        self._all: dict[str, bytes] = {}

    @property
    def cached_bytes(self) -> int:
        """How many bytes of objects memory holds now."""
        if self._directory is None:
            return sum(len(c) for c in self._all.values())
        return self._cache.size

    async def put(self, content: bytes) -> Digest:
        digest = digest_of(content)
        if self._directory is None:
            self._all.setdefault(digest, content)
            return digest
        path = self._directory / digest.removeprefix("sha256:")

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        try:
            await asyncio.to_thread(_write)
        except OSError as error:
            raise ObjectStoreUnavailable(f"the directory refused the object: {error}") from error
        self._cache.keep(digest, content)
        return digest

    async def get(self, digest: Digest) -> bytes | None:
        if self._directory is None:
            return self._all.get(digest)
        cached = self._cache.get(digest)
        if cached is not None:
            return cached
        path = self._directory / digest.removeprefix("sha256:")
        try:
            content = await asyncio.to_thread(path.read_bytes)
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError as error:
            raise ObjectStoreUnavailable(f"the directory could not be read: {error}") from error
        found = verified(digest, content, where=str(path))
        if found is not None:
            self._cache.keep(digest, found)
        return found
