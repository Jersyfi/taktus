"""The catalogue's rules and its one writer (ADR-0175, UC-14.6): an entry is admitted only when
signed by a key trusted for its tier, over the bytes it names; an installation is recorded with
its origin in the transaction of its ledger entry; nothing refused is recorded; and a half of an
adapter's maturity taken before its installation does not count for it."""

from __future__ import annotations

import ast
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClock

from taktus.adapters.driven.memory import (
    MemoryLedgerStore,
    MemoryObjectStore,
    MemoryPersistence,
    MemoryRepository,
)
from taktus.adapters.driven.signing import Ed25519Signatures
from taktus.components.catalog.application.service import (
    CATALOGUE_INSTALLED,
    CatalogueInstalls,
    InstallEntry,
    NotAdmitted,
)
from taktus.components.catalog.domain.model import (
    AdapterMaturity,
    CatalogueInstallation,
    Configuration,
    ConformanceResult,
    IndexEntry,
    RemovalResult,
    Tier,
    TrustedKey,
    Verdict,
)
from taktus.components.catalog.domain.service.catalogue import (
    admit,
    digest_of,
    payload,
    since_installed,
)
from taktus.components.ledger.application.service import ChainedLedger

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src" / "taktus"
AT = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)
TENANT = "t"
SIGNATURES = Ed25519Signatures()
BUNDLE = b"id: reminder\nversion: '1'\n"


def signed(document: dict[str, Any], seed: bytes) -> IndexEntry:
    """The entry, signed with the seed as an author signs it."""
    unsigned = IndexEntry.model_validate({k: v for k, v in document.items() if k != "signature"})
    signature = {
        "scheme": "ed25519",
        "key": SIGNATURES.public(seed),
        "value": SIGNATURES.sign(seed, payload(unsigned)),
    }
    return IndexEntry.model_validate({**unsigned.document(), "signature": signature})


def image(tier: str = "community", **changed: Any) -> dict[str, Any]:
    return {
        "id": "worker-shell",
        "kind": "image",
        "tier": tier,
        "version": "0.1.0",
        "summary": "Runs a shell script as a worker step.",
        "digest": "sha256:" + "b" * 64,
        "family": "worker",
        "contract": "worker/v1",
        "capabilities": ["shell.script"],
        "image": "registry.example/acme/worker-shell",
        **changed,
    }


def bundle(content: bytes = BUNDLE) -> dict[str, Any]:
    return {
        "id": "reminder",
        "kind": "bundle",
        "tier": "community",
        "version": "1",
        "summary": "A reminder, at level 2.",
        "digest": digest_of(content),
        "process": "reminder",
        "bundle": "bundles/reminder.yaml",
    }


@pytest.fixture
def author() -> bytes:
    return os.urandom(32)


def trust(seed: bytes, tier: Tier = Tier.COMMUNITY) -> tuple[TrustedKey, ...]:
    return (TrustedKey(key=SIGNATURES.public(seed), tier=tier, author="acme"),)


# --- admission ------------------------------------------------------------------------------------


def test_a_signed_entry_by_a_trusted_key_is_admitted_with_its_author(author: bytes) -> None:
    admission = admit(signed(image(), author), trust(author), SIGNATURES.verify)
    assert admission.admitted and admission.author == "acme" and admission.findings == ()


def test_an_unsigned_entry_is_refused(author: bytes) -> None:
    admission = admit(IndexEntry.model_validate(image()), trust(author), SIGNATURES.verify)
    assert not admission.admitted
    assert admission.findings == ("the entry is not signed",)


def test_a_key_the_operator_does_not_trust_is_refused(author: bytes) -> None:
    admission = admit(signed(image(), author), trust(os.urandom(32)), SIGNATURES.verify)
    assert not admission.admitted
    assert "is not one the operator trusts" in admission.findings[0]


def test_a_community_key_cannot_sign_a_reference_entry(author: bytes) -> None:
    admission = admit(signed(image("reference"), author), trust(author), SIGNATURES.verify)
    assert not admission.admitted
    assert admission.findings == (
        "its key is trusted for the community tier, and the entry states reference",
    )


def test_an_entry_changed_after_it_was_signed_is_refused(author: bytes) -> None:
    entry = signed(image(), author)
    tampered = entry.model_copy(update={"digest": "sha256:" + "c" * 64})
    admission = admit(tampered, trust(author), SIGNATURES.verify)
    assert not admission.admitted
    assert admission.findings == ("its signature does not verify over the entry",)


def test_a_bundle_is_admitted_only_over_the_bytes_it_was_signed_over(author: bytes) -> None:
    entry = signed(bundle(), author)
    assert admit(entry, trust(author), SIGNATURES.verify, BUNDLE).admitted
    other = admit(entry, trust(author), SIGNATURES.verify, BUNDLE + b"steps: []\n")
    assert other.findings == ("its bundle bundles/reminder.yaml is not the one it was signed over",)
    missing = admit(entry, trust(author), SIGNATURES.verify, None)
    assert missing.findings == ("its bundle bundles/reminder.yaml cannot be read beside the index",)


def test_an_index_never_states_verified() -> None:
    with pytest.raises(ValueError, match="tier"):
        IndexEntry.model_validate(image("verified"))


def test_the_payload_is_the_entry_without_its_signature_as_canonical_json(author: bytes) -> None:
    entry = signed(image(), author)
    document = entry.document()
    document.pop("signature")
    expected = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert payload(entry) == expected.encode("utf-8")


# --- the one writer -------------------------------------------------------------------------------


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(AT)
        self.persistence = MemoryPersistence()
        self.installations = MemoryRepository(self.persistence, CatalogueInstallation)
        self.ledger = ChainedLedger(MemoryLedgerStore(self.persistence), self.clock)
        self.objects = MemoryObjectStore()
        self.installs = CatalogueInstalls(
            SIGNATURES,
            self.installations,
            self.persistence,
            self.ledger,
            self.objects,
            self.clock,
        )


async def test_an_installed_image_is_recorded_with_its_origin_in_the_ledger(author: bytes) -> None:
    world = World()
    entry = signed(image(), author)
    installation, recorded = await world.installs.install(
        InstallEntry(TENANT, "acme", entry, trust(author), "idn_ada", adapter="worker.shell")
    )
    assert installation.id == "worker.shell" and installation.author == "acme"
    assert installation.entry == entry and installation.catalogue == "acme"
    assert recorded.kind == CATALOGUE_INSTALLED
    assert recorded.outcome == "community" and recorded.adapter == "worker.shell"
    assert recorded.refs.actor == "idn_ada"
    assert recorded.content_digest == installation.evidence
    evidence = json.loads(await world.objects.get(installation.evidence))
    assert evidence["entry"]["signature"]["key"] == SIGNATURES.public(author)
    assert evidence["catalogue"] == "acme" and evidence["author"] == "acme"
    assert evidence["entry"]["digest"] == entry.digest
    async with world.persistence.transaction(TENANT):
        assert await world.installations.get(TENANT, "worker.shell") == installation
        assert (await world.ledger.verify(TENANT)).intact


async def test_a_bundle_is_recorded_as_the_proposal_it_became(author: bytes) -> None:
    world = World()
    installation, recorded = await world.installs.install(
        InstallEntry(
            TENANT,
            "acme",
            signed(bundle(), author),
            trust(author),
            "idn_ada",
            bundle=BUNDLE,
            proposal="prp_1",
            process_version="reminder@1",
        )
    )
    assert installation.id == "process.reminder" and installation.proposal == "prp_1"
    assert recorded.adapter is None and recorded.refs.process_version == "reminder@1"


@pytest.mark.parametrize(
    ("entry", "adapter", "reason"),
    [
        (image(), "connector.shell", "a worker is installed as worker.<name>"),
        (image(), None, "an image is installed as an adapter identifier"),
        (image(tier="reference"), "worker.shell", "trusted for the community tier"),
    ],
)
async def test_nothing_refused_is_recorded(
    author: bytes, entry: dict[str, Any], adapter: str | None, reason: str
) -> None:
    world = World()
    with pytest.raises(NotAdmitted, match=reason):
        await world.installs.install(
            InstallEntry(
                TENANT, "acme", signed(entry, author), trust(author), "idn_ada", adapter=adapter
            )
        )
    assert await world.installs.installed(TENANT) == []
    async with world.persistence.transaction(TENANT):
        assert (await world.ledger.verify(TENANT)).entries == 0


def test_the_installation_has_exactly_one_writer() -> None:
    """Only the catalogue's install service constructs an installation in the source."""
    writers = []
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "CatalogueInstallation"
            ):
                writers.append(path.relative_to(SOURCE).as_posix())
    assert writers == ["components/catalog/application/service/catalogue.py"]


# --- what counts after the installation -----------------------------------------------------------

NOW = Configuration(adapter="worker.shell", serves=("shell.script",), version="0.1.0")


def maturity(at: datetime) -> AdapterMaturity:
    return AdapterMaturity(
        id="worker.shell",
        tenant=TENANT,
        family="worker",
        conformance=ConformanceResult(
            integration="worker.shell",
            family="worker",
            contract="worker/v1",
            taktus_version="0.0.0",
            configuration=NOW,
            outcome="passed",
            digest="sha256:" + "d" * 64,
            tested_at=at,
            actor="idn_ada",
        ),
        removal=RemovalResult(
            integration="worker.shell",
            family="worker",
            verdict=Verdict.CHANGED,
            tested_at=at,
            run_id="run_s01",
            configuration=NOW,
        ),
        updated_at=at,
    )


def installed_at(at: datetime, author: bytes) -> CatalogueInstallation:
    return CatalogueInstallation.model_validate(
        {
            "id": "worker.shell",
            "tenant": TENANT,
            "catalogue": "acme",
            "entry": signed(image(), author).document(),
            "author": "acme",
            "installed_at": at,
            "actor": "idn_ada",
            "evidence": "sha256:" + "e" * 64,
            "adapter": "worker.shell",
        }
    )


def test_a_half_taken_before_the_installation_does_not_count(author: bytes) -> None:
    record, dropped = since_installed(maturity(AT), installed_at(AT + timedelta(hours=1), author))
    assert record is not None and record.conformance is None and record.removal is None
    assert record.maturity(NOW).value == "experimental"
    assert len(dropped) == 2 and all("before the entry was installed" in d for d in dropped)


def test_halves_taken_after_the_installation_make_it_verified(author: bytes) -> None:
    record, dropped = since_installed(maturity(AT + timedelta(hours=2)), installed_at(AT, author))
    assert dropped == () and record is not None
    assert record.maturity(NOW).value == "verified"


def test_without_an_installation_the_record_is_as_it_is() -> None:
    record = maturity(AT)
    assert since_installed(record, None) == (record, ())
