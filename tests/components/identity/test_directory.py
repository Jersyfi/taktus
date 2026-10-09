"""UC-1.7: every command belongs to one identity — what the identity component guarantees.

A link is made only by the person, with a code from their Taktus account written in the channel
from the account, or by the organisation's identity source. One account maps to at most one
identity; one identity may hold accounts on many channels. Every link and every revocation is
a ledger entry, and a revoked account is from an unknown sender again (ADR-0040).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fakes.identity import FakeSource, directory

from taktus.components.identity.application.service import (
    IdentityExists,
    UnknownLink,
    UnknownTenant,
)
from taktus.components.identity.domain.model import CODE_VALIDITY, Identity, link_id
from taktus.ports.identity import SourceAnswer

REPO = "channel.repo"
CHAT = "channel.chat"


async def test_a_code_from_the_persons_account_written_from_the_account_links_it() -> None:
    given = directory()
    ada, _ = await given.person("default", "idn_ada", ("default", "finance"))
    assert await given.directory.resolve(REPO, "100200") is None, "nobody is linked yet"

    code = await given.code(ada)
    answer = await given.directory.unknown_sender(REPO, "100200", f"@taktus link {code}")
    assert answer.linked is not None and answer.linked.identity == "idn_ada"
    assert "linked" in answer.reply

    placed = await given.directory.resolve(REPO, "100200")
    assert placed is not None and placed.identity == "idn_ada"
    assert placed.org_path == ("default", "finance"), "the component sets the path"
    assert await given.kinds("default") == ["identity.created", "identity.linked"]


async def test_a_matching_name_or_address_links_nothing() -> None:
    """The failure UC-1.7 names: a link that appears without a confirmation."""
    given = directory()
    await given.person("default", "100200")
    await given.person("default", "ada@example.org")
    for said in ("I am 100200", "this is ada@example.org", "idn_ada", "@taktus link me"):
        answer = await given.directory.unknown_sender(REPO, "100200", said)
        assert answer.linked is None, said
        assert "does not know this account" in answer.reply
    assert await given.directory.resolve(REPO, "100200") is None
    assert await given.directory.resolve(REPO, "ada@example.org") is None
    assert await given.directory.links("default") == []


async def test_a_code_links_only_once_only_in_time_and_only_on_its_channel() -> None:
    given = directory()
    ada, _ = await given.person("default", "idn_ada")

    for_chat = await given.code(ada, CHAT)
    assert (await given.directory.unknown_sender(REPO, "100200", for_chat)).linked is None

    late = await given.code(ada)
    given.clock.current += CODE_VALIDITY + timedelta(seconds=1)
    assert (await given.directory.unknown_sender(REPO, "100200", late)).linked is None

    once = await given.code(ada)
    assert (await given.directory.unknown_sender(REPO, "100200", once)).linked is not None
    used = await given.directory.unknown_sender(REPO, "100300", once)
    assert used.linked is None, "a used code links nothing more"
    assert await given.directory.resolve(REPO, "100300") is None


async def test_one_account_maps_to_at_most_one_identity_and_one_identity_to_many() -> None:
    given = directory(("default", "acme"))
    ada, _ = await given.person("default", "idn_ada")
    bob, _ = await given.person("acme", "idn_bob")

    assert (await given.directory.unknown_sender(REPO, "100200", await given.code(ada))).linked
    second = await given.directory.unknown_sender(REPO, "100200", await given.code(bob))
    assert second.linked is None and "linked to another" in second.reply, "a second link"
    placed = await given.directory.resolve(REPO, "100200")
    assert placed is not None and placed.identity == "idn_ada"
    assert await given.directory.links("acme") == []

    assert (await given.directory.unknown_sender(CHAT, "U42", await given.code(ada, CHAT))).linked
    on_chat = await given.directory.resolve(CHAT, "U42")
    assert on_chat is not None and on_chat.identity == "idn_ada", "one identity, two channels"
    assert len(await given.directory.links("default")) == 2


async def test_every_link_and_every_removal_is_a_ledger_entry_and_revoked_is_unknown() -> None:
    given = directory()
    ada, _ = await given.person("default", "idn_ada")
    await given.person("default", "idn_admin")
    await given.directory.unknown_sender(REPO, "100200", await given.code(ada))

    (link,) = await given.directory.links("default")
    assert link.id == link_id(REPO, "100200") and link.active and link.identity == "idn_ada"
    revoked = await given.directory.revoke("default", link.id, by="idn_admin")
    assert not revoked.active and revoked.revoked_by == "idn_admin"
    assert await given.directory.resolve(REPO, "100200") is None, "an unknown sender again"
    (kept,) = await given.directory.links("default")
    assert not kept.active, "the administrator still sees the revoked link"
    with pytest.raises(UnknownLink):
        await given.directory.revoke("default", link.id)

    async with given.persistence.transaction("default"):
        entries = await given.ledger.entries("default")
    linked = [e for e in entries if e.kind == "identity.linked"]
    unlinked = [e for e in entries if e.kind == "identity.unlinked"]
    assert [e.outcome for e in linked] == ["confirmed"] and linked[0].refs.actor == "idn_ada"
    assert [e.outcome for e in unlinked] == ["revoked"]
    assert unlinked[0].refs.actor == "idn_admin"
    assert all(e.content_digest for e in linked + unlinked)
    assert "100200" not in str([e.document() for e in entries]), "no account in the ledger"

    # Revoked, the account can be linked again, by a new confirmation only.
    again = await given.directory.unknown_sender(REPO, "100200", await given.code(ada))
    assert again.linked is not None


async def test_the_organisations_identity_source_links_what_it_answers() -> None:
    source = FakeSource(
        {
            (REPO, "100200"): SourceAnswer(
                tenant="default", identity="idn_carol", org_path=("default", "ops")
            ),
            (REPO, "100999"): SourceAnswer(tenant="elsewhere", identity="idn_x", org_path=("x",)),
        }
    )
    given = directory(source=source)
    placed = await given.directory.resolve(REPO, "100200")
    assert placed is not None and placed.identity == "idn_carol"
    assert placed.org_path == ("default", "ops")
    (link,) = await given.directory.links("default")
    assert link.origin == "source"
    assert await given.kinds("default") == ["identity.created", "identity.linked"]
    assert await given.directory.resolve(REPO, "100200") is not None
    assert source.asked == [(REPO, "100200")], "once linked, the link answers"
    assert await given.directory.resolve(REPO, "100999") is None, "a tenant not served"
    assert await given.directory.resolve(REPO, "100500") is None, "the source knows nobody"


async def test_an_account_key_proves_its_identity_and_a_new_key_retires_the_old() -> None:
    given = directory()
    _, first = await given.person("default", "idn_ada")
    assert await given.directory.authenticate("tka_" + "0" * 64) is None
    assert await given.directory.authenticate("") is None
    second = await given.directory.issue_key("default", "idn_ada")
    assert await given.directory.authenticate(first) is None
    who = await given.directory.authenticate(second)
    assert who is not None and who.identity == "idn_ada"


async def test_an_identity_belongs_to_a_served_tenant_and_exists_once() -> None:
    given = directory()
    with pytest.raises(UnknownTenant):
        await given.directory.add("acme", "idn_ada", ("acme",))
    await given.directory.add("default", "idn_ada", ("default",))
    with pytest.raises(IdentityExists):
        await given.directory.add("default", "idn_ada", ("default",))
    with pytest.raises(ValueError, match="starts at its tenant"):
        Identity.model_validate(
            {
                "id": "idn_b",
                "tenant": "default",
                "org_path": ["acme"],
                "created_at": "2026-10-09T00:00:00Z",
            }
        )
    assert await given.directory.identity("default", "idn_ada") is not None
    assert await given.directory.identity("default", "idn_nobody") is None
    assert await given.directory.identity("acme", "idn_ada") is None
