"""How the catalog checks a signature, without knowing the scheme's library (ADR-0175 §2).

An entry of a catalogue is signed with Ed25519 over its canonical form. The composition root
binds the instance's signing adapter, which verifies a submission's signature the same way
(ADR-0118). Signing is the author's act and never the instance's, so the port only verifies.
"""

from __future__ import annotations

from typing import Protocol


class Signatures(Protocol):
    def verify(self, public: str, payload: bytes, signature: str) -> bool:
        """Whether `signature` (base64url) over `payload` verifies under the public key
        (base64url). False for a key or a signature that cannot be read."""
        ...
