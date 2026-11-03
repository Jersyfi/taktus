"""The Python binding of the catalogue contract matches `Catalogue.json`
(`contracts/catalogue/v1`, ADR-0175).

Every valid example reads into the catalog component's model and back unchanged, and every
signature in them verifies over the payload the README defines. Every must-fail example is
refused by the model, but one: an entry without a signature is read, so that the catalogue can
list it with why it is refused, and admission refuses it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from taktus.adapters.driven.signing import Ed25519Signatures
from taktus.components.catalog.domain.model import CatalogueIndex, IndexEntry, Tier, Trust
from taktus.components.catalog.domain.service.catalogue import admit, payload

from .test_shared_kernel_binding import example_cases, load

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "contracts" / "catalogue" / "v1"
SCHEMA: dict[str, Any] = json.loads((CATALOGUE / "Catalogue.json").read_text(encoding="utf-8"))
BINDINGS: dict[str, type[IndexEntry] | type[CatalogueIndex] | type[Trust]] = {
    "entry": IndexEntry,
    "index": CatalogueIndex,
    "trust": Trust,
}
READ_TO_BE_REFUSED = {"entry/invalid/without-a-signature.json"}


def test_the_tiers_are_the_model_s_and_verified_is_none_of_them() -> None:
    assert SCHEMA["$defs"]["Tier"]["enum"] == [t.value for t in Tier]
    assert "verified" not in SCHEMA["$defs"]["Tier"]["enum"]


@pytest.mark.parametrize(
    ("path", "valid"),
    example_cases(CATALOGUE / "examples"),
    ids=lambda p: p.relative_to(CATALOGUE / "examples").as_posix() if isinstance(p, Path) else "",
)
def test_examples_through_the_binding(path: Path, valid: bool) -> None:
    binding = BINDINGS[path.parent.parent.name]
    data = load(path)
    named = path.relative_to(CATALOGUE / "examples").as_posix()
    if valid:
        assert binding.model_validate(data).document() == data
        return
    if named in READ_TO_BE_REFUSED:
        entry = IndexEntry.model_validate(data)
        assert not admit(entry, (), Ed25519Signatures().verify).admitted
        return
    with pytest.raises(ValidationError):
        binding.model_validate(data)


def test_every_signature_in_the_examples_verifies_over_the_payload() -> None:
    signatures = Ed25519Signatures()
    seen = 0
    for path in sorted((CATALOGUE / "examples" / "entry" / "valid").glob("*.json")):
        entry = IndexEntry.model_validate(load(path))
        assert entry.signature is not None
        assert signatures.verify(entry.signature.key, payload(entry), entry.signature.value)
        seen += 1
    assert seen >= 2
