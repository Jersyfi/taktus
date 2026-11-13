"""A tenant's administrative acts on the HTTP surface, for the web app's administration page
(ADR-0279, UC-10.2): every act the command line's `taktusctl identity` and `taktusctl units`
offer, by the same use cases, with the same entries in the ledger.

- `POST /administration/identities` — add an identity; its first account key is answered once.
- `POST /administration/identities/{identity}/key` — a new account key, answered once.
- `POST /administration/identities/{identity}/agent-key` — a new agent key, answered once.
- `PUT /administration/identities/{identity}/roles` — the identity's roles.
- `GET /administration/links`, `DELETE /administration/links/{link}` — every channel link,
  and one revoked.
- `GET /administration/rights`, `PUT|DELETE /administration/rights/{role}/{right}` — what each
  role may do, granted and withdrawn; a right is a role's, never a person's (UC-7.3).
- `GET /administration/units`, `PUT|DELETE /administration/units/{unit}` — the quotas per
  organisational unit (ADR-0166).
- `GET /administration/health` — the instance's health: its release, whether it may receive
  traffic and why not, the roles it serves, and the tenant's backup, alerts and incidents
  (ADR-0295).
- `POST /administration/update` — an update of Taktus prepared as a plan draft, which a person
  works out and commissions in the plan dialogue; commissioning applies nothing (ADR-0296).

Each needs an account key, or the web app's session, of an identity whose roles hold the
right `tenant.administer`. The tenants themselves are `/administration/tenants`, for the
holder of the instance's administration key (ADR-0104).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from taktus.adapters.driving.rest.operation import backup_standing
from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.command.application.service import PlanningError
from taktus.components.command.domain.service.guided import Mode
from taktus.components.governance.application.service import SetOrgUnitQuota
from taktus.components.identity.application.service import IdentityError
from taktus.components.identity.domain.model import Right
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"
NOT_ADMIN = "an administrative act needs a role holding tenant.administer"
MONEY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([a-z]{3})$")


class AddBody(BaseModel):
    identity: str = Field(min_length=1)
    org_path: list[str] = Field(default_factory=list, description="Below the tenant.")
    roles: list[str] = Field(default_factory=list)


class RolesBody(BaseModel):
    roles: list[str] = Field(default_factory=list)


class UpdateBody(BaseModel):
    to: str = Field(
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$",
        description="The release to update to, as 1.0.1: one release after the running one.",
    )
    said: str = Field(default="", max_length=2000, description="Why, in your words.")


def release() -> str:
    """The release of Taktus this process runs, as its package names it."""
    try:
        return version("taktus")
    except PackageNotFoundError:
        return "unknown"


class QuotaBody(BaseModel):
    concurrent_runs: int | None = Field(default=None, ge=1)
    budget: list[str] = Field(default_factory=list, description="As 250eur, once a currency.")
    check_every_seconds: int = Field(default=900, ge=1)


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["administration"])
    common: dict[int | str, dict[str, Any]] = {
        400: {"description": "Refused; the detail says why.", **PROBLEM},
        401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
        403: {"description": "Your roles do not hold tenant.administer.", **PROBLEM},
        422: {"description": "A parameter does not validate.", **PROBLEM},
    }

    async def admin(authorization: str | None) -> Resolution | JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        if Right.ADMINISTER not in await services.identities.rights(who):
            return problem(403, NOT_ADMIN)
        return who

    @routes.post(
        "/administration/identities",
        summary="Add an identity",
        description="A new identity of your tenant with its place in the structure and its "
        "roles; its first account key is answered once and kept only as a digest "
        "(`identity.created`).",
        status_code=201,
        responses={201: {"description": "The identity and its key."}, **common},
    )
    async def add(body: AddBody, authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            made, key = await services.identities.add(
                who.tenant,
                body.identity,
                (who.tenant, *body.org_path),
                by=who.identity,
                roles=body.roles,
            )
        except (IdentityError, ValueError) as error:
            return problem(400, str(error))
        return JSONResponse(
            {"identity": made.id, "org_path": list(made.org_path), "key": key}, status_code=201
        )

    @routes.post(
        "/administration/identities/{identity}/key",
        summary="Issue a new account key",
        description="The old key proves nothing from now on, and every browser session "
        "exchanged for it ends (`identity.key_issued`).",
        responses={200: {"description": "The key, once."}, **common},
    )
    async def key(identity: str, authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            issued = await services.identities.issue_key(who.tenant, identity, by=who.identity)
        except IdentityError as error:
            return problem(400, str(error))
        return JSONResponse({"identity": identity, "key": issued})

    @routes.post(
        "/administration/identities/{identity}/agent-key",
        summary="Issue a new agent key",
        description="The key the person's own agent proves them with on the MCP surface "
        "(`identity.agent_key_issued`, ADR-0131).",
        responses={200: {"description": "The agent key, once."}, **common},
    )
    async def agent_key(identity: str, authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            issued = await services.identities.issue_agent_key(
                who.tenant, identity, by=who.identity
            )
        except IdentityError as error:
            return problem(400, str(error))
        return JSONResponse({"identity": identity, "agent_key": issued})

    @routes.put(
        "/administration/identities/{identity}/roles",
        summary="Set an identity's roles",
        description="The roles it holds from now on; none clears them (`identity.roles_set`).",
        responses={200: {"description": "The identity's roles."}, **common},
    )
    async def roles(
        identity: str, body: RolesBody, authorization: str | None = Header(default=None)
    ) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            changed = await services.identities.set_roles(
                who.tenant, identity, body.roles, by=who.identity
            )
        except (IdentityError, ValueError) as error:
            return problem(400, str(error))
        return JSONResponse({"identity": changed.id, "roles": list(changed.roles)})

    @routes.get(
        "/administration/links",
        summary="Every channel link",
        description="Each account mapped to an identity, active or revoked (UC-1.7).",
        responses={200: {"description": "The links."}, **common},
    )
    async def links(authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        listed = await services.identities.links(who.tenant)
        return JSONResponse({"links": [link.document() for link in listed]})

    @routes.delete(
        "/administration/links/{link}",
        summary="Revoke a channel link",
        description="The next event from the account is from an unknown sender "
        "(`identity.unlinked`).",
        responses={200: {"description": "The revoked link."}, **common},
    )
    async def revoke(link: str, authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            revoked = await services.identities.revoke(who.tenant, link, by=who.identity)
        except IdentityError as error:
            return problem(400, str(error))
        return JSONResponse(revoked.document())

    @routes.get(
        "/administration/rights",
        summary="What each role may do",
        description="Every role that holds a right, with its rights, and every right there is.",
        responses={200: {"description": "The rights."}, **common},
    )
    async def rights(authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        granted = await services.identities.granted(who.tenant)
        return JSONResponse(
            {
                "roles": [{"role": r.id, "rights": [str(x) for x in r.rights]} for r in granted],
                "rights": [str(r) for r in Right],
            }
        )

    async def set_right(
        role: str, right: str, authorization: str | None, *, held: bool
    ) -> JSONResponse:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        try:
            chosen = Right(right)
        except ValueError:
            return problem(400, f"there is no right {right!r}")
        try:
            act = services.identities.grant if held else services.identities.withdraw
            changed = await act(who.tenant, role, chosen, by=who.identity)
        except (IdentityError, ValueError) as error:
            return problem(400, str(error))
        return JSONResponse({"role": changed.id, "rights": [str(x) for x in changed.rights]})

    @routes.put(
        "/administration/rights/{role}/{right}",
        summary="Grant a role a right",
        description="`identity.right_granted`; a right is never granted to a person.",
        responses={200: {"description": "The role's rights."}, **common},
    )
    async def grant(role: str, right: str, authorization: str | None = Header(default=None)) -> Any:
        return await set_right(role, right, authorization, held=True)

    @routes.delete(
        "/administration/rights/{role}/{right}",
        summary="Withdraw a right from a role",
        description="`identity.right_withdrawn`.",
        responses={200: {"description": "The role's rights."}, **common},
    )
    async def withdraw(
        role: str, right: str, authorization: str | None = Header(default=None)
    ) -> Any:
        return await set_right(role, right, authorization, held=False)

    @routes.get(
        "/administration/units",
        summary="The quotas per organisational unit",
        description="How many runs of each unit may hold a runner's place at once, and what "
        "its runs may commit per month (ADR-0166).",
        responses={200: {"description": "The quotas."}, **common},
    )
    async def units(authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        quotas = await services.org_units.quotas(who.tenant)
        return JSONResponse({"quotas": [q.document() for q in quotas]})

    @routes.put(
        "/administration/units/{unit}",
        summary="Set a unit's quota",
        description="A limit is a unit's, never a person's: a unit named like an identity is "
        "refused (principle 14).",
        responses={200: {"description": "The quota."}, **common},
    )
    async def set_unit(
        unit: str, body: QuotaBody, authorization: str | None = Header(default=None)
    ) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        budget: dict[str, float] = {}
        for one in body.budget:
            matched = MONEY.match(one.strip().lower())
            if matched is None or matched.group(2) in budget:
                return problem(400, f"{one!r}: a budget is <amount><currency>, once a currency")
            budget[matched.group(2)] = float(matched.group(1))
        try:
            quota = await services.org_units.set(
                SetOrgUnitQuota(
                    tenant=who.tenant,
                    org_unit=unit,
                    concurrent_runs=body.concurrent_runs,
                    budget=budget or None,
                    check_every_seconds=body.check_every_seconds,
                ),
                by=who.identity,
            )
        except ValueError as error:
            return problem(400, str(error))
        return JSONResponse(quota.document())

    @routes.delete(
        "/administration/units/{unit}",
        summary="Take a unit's quota away",
        description="The unit holds none from now on.",
        responses={200: {"description": "Cleared."}, **common},
    )
    async def clear_unit(unit: str, authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        await services.org_units.set(
            SetOrgUnitQuota(tenant=who.tenant, org_unit=unit), by=who.identity
        )
        return JSONResponse({"unit": unit, "cleared": True})

    @routes.get(
        "/administration/health",
        summary="The instance's health",
        description="The release this process runs, whether it may receive traffic and, if "
        "not, why, the roles it serves and whether it leads; for your tenant, how the backup "
        "stands, how many alerts are in effect and how many incidents are open (ADR-0295). "
        "`taktusctl health` shows the same.",
        responses={200: {"description": "The instance's health."}, **common},
    )
    async def health(authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        reason = await services.ready()
        backup = await services.operation.backup(who.tenant)
        alerts = await services.operation.alerts(who.tenant)
        incidents = await services.operation.incidents(who.tenant)
        return JSONResponse(
            {
                "release": release(),
                "ready": reason is None,
                "reason": reason,
                "roles": list(services.roles),
                "leading": services.leading,
                "backup": backup_standing(backup),
                "alerts_in_effect": sum(1 for a in alerts if a.alert.in_effect and not a.closed),
                "incidents_open": sum(1 for i in incidents if i.closed_at is None),
            }
        )

    @routes.post(
        "/administration/update",
        summary="Prepare an update of Taktus as a plan",
        description="A plan draft for the update to the release named: a backup, the upgrade "
        "and the check, each a person's step from the upgrading guide, with the way back to the "
        "release before. You state when it is due and at which level, and commission it in the "
        "plan dialogue; commissioning records `instance.update_commissioned` and applies "
        "nothing: a person carries the steps out (ADR-0296, ADR-0013 D).",
        status_code=201,
        responses={201: {"description": "The draft, in the guided mode."}, **common},
    )
    async def update(body: UpdateBody, authorization: str | None = Header(default=None)) -> Any:
        who = await admin(authorization)
        if isinstance(who, JSONResponse):
            return who
        said = body.said.strip() or f"update Taktus to {body.to}"
        try:
            draft = await services.planning.open(
                who.tenant,
                who.identity,
                who.org_path,
                said,
                act="instance.update",
                arguments={"to": body.to},
            )
        except PlanningError as error:
            return problem(400, str(error))
        return JSONResponse(services.planning.view(draft, Mode.GUIDED), status_code=201)

    return routes
