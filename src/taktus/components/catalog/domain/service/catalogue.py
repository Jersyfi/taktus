"""The rules of the catalogue (ADR-0175): what is signed, when an entry is admitted, and which
records count for an adapter installed from it.

- **The signed payload** is the entry without its `signature`, as canonical JSON: keys sorted,
  no whitespace between tokens, UTF-8 without escaping.
- **Admission** asks four things of an entry: that it is signed; that its key is one the
  operator trusts for the tier it states; that the signature verifies; and, for a bundle, that
  the bytes are the ones it was signed over. Every reason that fails is named.
- **Counted since the installation**: a conformance pass or a removal test taken before an
  entry was installed was taken on what stood behind the identifier before, and does not count
  for it (§5). The record is read as if neither half had been taken.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence

from taktus.components.catalog.domain.model.catalogue import (
    Admission,
    CatalogueInstallation,
    IndexEntry,
    TrustedKey,
)
from taktus.components.catalog.domain.model.maturity import AdapterMaturity

type Verify = Callable[[str, bytes, str], bool]
"""(public key, payload, signature) → whether the signature verifies."""

FAMILIES = {"worker": "worker.", "connector": "connector.", "model": "model."}
BEFORE = "the {half} was taken before the entry was installed on {at}, on what stood there before"


def payload(entry: IndexEntry) -> bytes:
    """The bytes a signature covers."""
    document = entry.document()
    document.pop("signature", None)
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest_of(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def admit(
    entry: IndexEntry,
    trusted: Sequence[TrustedKey],
    verify: Verify,
    bundle: bytes | None = None,
) -> Admission:
    """Whether the instance may install the entry. `bundle` is the bundle file's bytes, None
    where it could not be read; it is not asked of an image."""
    findings: list[str] = []
    signature = entry.signature
    author: str | None = None
    if signature is None:
        findings.append("the entry is not signed")
    else:
        keys = [k for k in trusted if k.key == signature.key]
        if not keys:
            findings.append(f"its key {signature.key} is not one the operator trusts")
        elif not any(k.tier == entry.tier for k in keys):
            tiers = ", ".join(sorted(str(k.tier) for k in keys))
            findings.append(
                f"its key is trusted for the {tiers} tier, and the entry states {entry.tier}"
            )
        else:
            author = next(k.author for k in keys if k.tier == entry.tier)
        if not verify(signature.key, payload(entry), signature.value):
            findings.append("its signature does not verify over the entry")
    if entry.kind == "bundle":
        if bundle is None:
            findings.append(f"its bundle {entry.bundle} cannot be read beside the index")
        elif digest_of(bundle) != entry.digest:
            findings.append(f"its bundle {entry.bundle} is not the one it was signed over")
    if findings:
        return Admission(admitted=False, findings=tuple(findings))
    return Admission(admitted=True, author=author)


def fits(entry: IndexEntry, adapter: str) -> str | None:
    """Why an image entry cannot be bound to the adapter identifier; None where it can."""
    if entry.kind != "image" or entry.family is None:
        return "a bundle is installed as a proposal, not as an adapter"
    prefix = FAMILIES[entry.family]
    if not adapter.startswith(prefix) or len(adapter) == len(prefix):
        return f"a {entry.family} is installed as {prefix}<name>, not as {adapter!r}"
    return None


def since_installed(
    record: AdapterMaturity | None, installation: CatalogueInstallation | None
) -> tuple[AdapterMaturity | None, tuple[str, ...]]:
    """The record with every half taken before the installation left out, and what was left
    out, in words. Without an installation the record is as it is."""
    if record is None or installation is None:
        return record, ()
    at = installation.installed_at
    dropped: list[str] = []
    conformance, removal = record.conformance, record.removal
    if conformance is not None and conformance.tested_at < at:
        conformance = None
        dropped.append(BEFORE.format(half="conformance run", at=at.isoformat()))
    if removal is not None and removal.tested_at < at:
        removal = None
        dropped.append(BEFORE.format(half="removal test", at=at.isoformat()))
    if not dropped:
        return record, ()
    return record.model_copy(update={"conformance": conformance, "removal": removal}), tuple(
        dropped
    )
