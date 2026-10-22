"""Signatures over Ed25519: what a sender signs its submissions to an intake with, and what the
intake verifies them by (ADR-0118).

A private key is derived from a seed of thirty-two bytes, which the reporting component keeps
(`Pseudonyms.signing`). A public key and a signature are text: base64url without padding, of
the 32 raw bytes of the public key and the 64 of the signature. Nothing is stored here, and no
key is ever logged.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

SCHEME = "ed25519"


def _text(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _raw(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Ed25519Signatures:
    """The reporting component's `Signatures` port over Ed25519."""

    def public(self, seed: bytes) -> str:
        key = Ed25519PrivateKey.from_private_bytes(seed[:32]).public_key()
        return _text(key.public_bytes(Encoding.Raw, PublicFormat.Raw))

    def sign(self, seed: bytes, payload: bytes) -> str:
        return _text(Ed25519PrivateKey.from_private_bytes(seed[:32]).sign(payload))

    def verify(self, public: str, payload: bytes, signature: str) -> bool:
        try:
            key = Ed25519PublicKey.from_public_bytes(_raw(public))
            key.verify(_raw(signature), payload)
        except (InvalidSignature, ValueError, binascii.Error):
            return False
        return True
