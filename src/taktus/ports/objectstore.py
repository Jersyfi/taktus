"""Content-addressed storage of artifact bytes.

The ledger references content by digest and never stores it (ADR-0006); this is where the
content goes. An object is written once under the digest of its bytes and read by that digest.
"""

from __future__ import annotations

from typing import Protocol

from taktus.shared.v1 import Digest


class ObjectStore(Protocol):
    async def put(self, content: bytes) -> Digest:
        """Store the bytes; the digest returned is `sha256:` over exactly these bytes."""
        ...

    async def get(self, digest: Digest) -> bytes | None: ...
