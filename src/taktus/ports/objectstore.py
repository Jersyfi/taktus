"""Content-addressed storage of artifact bytes.

The ledger references content by digest and never stores it (ADR-0006); this is where the
content goes. An object is written once under the digest of its bytes and read by that digest.
Every adapter passes one suite (`tests/adapters/objectstore/`, ADR-0165 §2).
"""

from __future__ import annotations

from typing import Protocol

from taktus.shared.v1 import Digest


class ObjectStoreUnavailable(Exception):
    """The store could not be reached or refused the request. Never the same as an object
    that is absent: "the content is gone" and "the store is down" lead to different actions
    (ADR-0165 §2)."""


class ObjectStore(Protocol):
    async def put(self, content: bytes) -> Digest:
        """Store the bytes; the digest returned is `sha256:` over exactly these bytes. Raises
        `ObjectStoreUnavailable` when they could not be stored."""
        ...

    async def get(self, digest: Digest) -> bytes | None:
        """The bytes stored under the digest; None when there are none, or when the bytes found
        do not hash to it. Raises `ObjectStoreUnavailable` when the store cannot answer."""
        ...
