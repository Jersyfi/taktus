"""The provisional operator identity (DEC-0013): configured, not authenticated, and honest
about it in every answer."""

from __future__ import annotations

from taktus.adapters.driven.identity import ProvisionalOperatorIdentity


async def test_one_tenant_places_every_sender_as_its_operator() -> None:
    resolver = ProvisionalOperatorIdentity({"default": "idn_owner"})
    for account in ("100200", "somebody-else", "bot"):
        resolution = await resolver.resolve("channel.repo", account)
        assert resolution is not None
        assert resolution.tenant == "default" and resolution.identity == "idn_owner"
        assert resolution.org_path == ("default",)
        assert resolution.provisional is True, "never mistaken for an authenticated identity"


async def test_several_tenants_place_nobody_without_a_tenant() -> None:
    """Guessing a tenant is what the provisional identity exists to stop."""
    resolver = ProvisionalOperatorIdentity({"default": "idn_owner", "acme": "idn_acme"})
    assert await resolver.resolve("channel.repo", "100200") is None
    named = await resolver.resolve("channel.cli", "local", tenant="acme")
    assert named is not None and named.identity == "idn_acme"
    assert await resolver.resolve("channel.cli", "local", tenant="nowhere") is None
    assert resolver.tenants == ("default", "acme")


async def test_nothing_configured_places_nobody() -> None:
    resolver = ProvisionalOperatorIdentity({})
    assert await resolver.resolve("channel.repo", "100200") is None
    assert await resolver.resolve("channel.cli", "local", tenant="default") is None
