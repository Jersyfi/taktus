"""The inventory of administrative acts, each in both ways in (ADR-0279, UC-10.2).

Every act an administrator does on a tenant is named here once, with the command line's
command, the HTTP surface's operation the web app calls, and the web app's page where its form
or its list is marked `data-act="<act>"`. `tests/adapters/test_administration_inventory.py`
walks the list and finds each in all three. An act added to one way in and not to the other
fails it.

Every act is a ledger entry naming the identity that did it, by the use case both ways call.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Act:
    name: str
    what: str
    cli: tuple[str, ...]
    """The command line's words after `taktusctl`."""
    method: str
    path: str
    """The HTTP surface's operation, as `api/openapi.yaml` names it."""
    page: str
    """The web app's route, under `#/`."""


ACTS: tuple[Act, ...] = (
    Act(
        "tenant.list",
        "the instance's tenants",
        ("tenant", "list"),
        "get",
        "/administration/tenants",
        "tenants",
    ),
    Act(
        "tenant.create",
        "create a tenant",
        ("tenant", "create"),
        "post",
        "/administration/tenants",
        "tenants",
    ),
    Act(
        "tenant.rename",
        "rename a tenant",
        ("tenant", "rename"),
        "patch",
        "/administration/tenants/{tenant}",
        "tenants",
    ),
    Act(
        "tenant.export",
        "export a tenant to one file",
        ("tenant", "export"),
        "get",
        "/administration/tenants/{tenant}/export",
        "tenants",
    ),
    Act(
        "tenant.import",
        "import a tenant's export, checked by its chains",
        ("tenant", "import"),
        "post",
        "/administration/tenants/import",
        "tenants",
    ),
    Act(
        "identity.add",
        "add an identity with its first key",
        ("identity", "add"),
        "post",
        "/administration/identities",
        "administration",
    ),
    Act(
        "identity.key",
        "a new account key",
        ("identity", "key"),
        "post",
        "/administration/identities/{identity}/key",
        "administration",
    ),
    Act(
        "identity.agent-key",
        "a new agent key",
        ("identity", "agent-key"),
        "post",
        "/administration/identities/{identity}/agent-key",
        "administration",
    ),
    Act(
        "identity.roles",
        "set an identity's roles",
        ("identity", "roles"),
        "put",
        "/administration/identities/{identity}/roles",
        "administration",
    ),
    Act(
        "identity.links",
        "every channel link",
        ("identity", "links"),
        "get",
        "/administration/links",
        "administration",
    ),
    Act(
        "identity.revoke",
        "revoke a channel link",
        ("identity", "revoke"),
        "delete",
        "/administration/links/{link}",
        "administration",
    ),
    Act(
        "identity.rights",
        "what each role may do",
        ("identity", "rights"),
        "get",
        "/administration/rights",
        "administration",
    ),
    Act(
        "identity.grant",
        "grant a role a right",
        ("identity", "grant"),
        "put",
        "/administration/rights/{role}/{right}",
        "administration",
    ),
    Act(
        "identity.withdraw",
        "withdraw a right from a role",
        ("identity", "withdraw"),
        "delete",
        "/administration/rights/{role}/{right}",
        "administration",
    ),
    Act(
        "units.show",
        "the quotas per unit",
        ("units", "show"),
        "get",
        "/administration/units",
        "administration",
    ),
    Act(
        "units.set",
        "set a unit's quota",
        ("units", "set"),
        "put",
        "/administration/units/{unit}",
        "administration",
    ),
    Act(
        "units.clear",
        "take a unit's quota away",
        ("units", "clear"),
        "delete",
        "/administration/units/{unit}",
        "administration",
    ),
    Act("structure.show", "the structure", ("structure", "show"), "get", "/structure", "structure"),
    Act(
        "structure.levels",
        "name the levels",
        ("structure", "levels"),
        "put",
        "/structure/levels",
        "structure",
    ),
    Act(
        "structure.unit",
        "add a unit",
        ("structure", "unit"),
        "post",
        "/structure/units",
        "structure",
    ),
    Act(
        "structure.place",
        "place or move an object",
        ("structure", "place"),
        "put",
        "/structure/placements/{kind}/{name}",
        "structure",
    ),
    Act(
        "structure.knowledge",
        "configure a unit's knowledge system",
        ("structure", "knowledge"),
        "put",
        "/structure/knowledge/{unit}",
        "structure",
    ),
    Act(
        "structure.where",
        "where something is documented",
        ("structure", "where"),
        "get",
        "/structure/filings/{kind}/{name}",
        "structure",
    ),
    Act(
        "project.create",
        "create a project",
        ("structure", "project"),
        "post",
        "/projects",
        "structure",
    ),
    Act(
        "adapter.list",
        "every adapter with its maturity",
        ("conformance", "list"),
        "get",
        "/register",
        "register",
    ),
    Act(
        "adapter.stop",
        "stop an adapter",
        ("stop", "adapter"),
        "post",
        "/register/{adapter}/stop",
        "register",
    ),
    Act(
        "backup.list",
        "the newest backups with their age",
        ("backup", "list"),
        "get",
        "/backup",
        "backup",
    ),
    Act(
        "instance.health",
        "the instance's health",
        ("health",),
        "get",
        "/administration/health",
        "health",
    ),
    Act(
        "instance.update",
        "prepare an update of Taktus as a plan",
        ("update", "prepare"),
        "post",
        "/administration/update",
        "health",
    ),
)
