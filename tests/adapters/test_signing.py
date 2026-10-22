"""The signature scheme a sender signs its submissions with (ADR-0118)."""

from __future__ import annotations

from taktus.adapters.driven.signing import Ed25519Signatures

SEED, OTHER = b"s" * 32, b"o" * 32


def test_a_signature_verifies_under_its_key_and_nothing_else() -> None:
    signing = Ed25519Signatures()
    key, signature = signing.public(SEED), signing.sign(SEED, b"payload")
    assert signing.public(SEED) == key, "the same seed, the same key"
    assert signing.verify(key, b"payload", signature)
    assert not signing.verify(key, b"payloaD", signature), "a changed payload"
    assert not signing.verify(signing.public(OTHER), b"payload", signature), "another key"
    assert not signing.verify(key, b"payload", signing.sign(OTHER, b"payload"))


def test_a_key_or_a_signature_that_cannot_be_read_does_not_verify() -> None:
    signing = Ed25519Signatures()
    signature = signing.sign(SEED, b"payload")
    assert not signing.verify("not a key", b"payload", signature)
    assert not signing.verify(signing.public(SEED), b"payload", "%%%")
    assert not signing.verify("", b"payload", "")
