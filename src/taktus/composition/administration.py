"""An administrative act asked in dialogue, carried out as a plan a person commissions (ADR-0296,
UC-10.2, UC-1.2).

A plan draft may carry an administrative act: one of the acts the inventory names
(`adapters/driving/inventory.py`), with its arguments. Choosing the act gives the draft its
steps and their estimates; the person still states when it is due and at which autonomy level,
and why. Commissioning it is three things in order:

1. **Checked before anything is written.** The draft lacks no part and every step can be
   estimated (ADR-0237); the identity that commissions holds the right the same act needs by
   hand on the HTTP surface, `tenant.administer` (ADR-0279 §2), and no wider one is asked or
   given; the act's target exists. Each refusal names what it found.
2. **The plan commissioned.** The plan dialogue records `plan.commissioned`, naming the plan and
   the identity.
3. **The act carried out by the use case both ways in call**, with the commissioner as its
   actor, after `administration.carried_out` names the plan, the identity and the act with its
   target. The use case records its own entry, as it does by hand.

An update of Taktus (`instance.update`) is prepared the same way, and commissioning it applies
nothing: no instance administers the platform it runs on (ADR-0025), and a version Taktus built
is put into production by a person or another instance (ADR-0013 D). Its steps are a person's —
a backup, the upgrade, the check — with the way back to the version before as the fallback, all
from the upgrading guide, which needs no Taktus (ADR-0013 C). Commissioning records
`instance.update_commissioned` with the version, and the person carries the steps out.

This is wiring: a draft of the `command` component becomes an act of the `identity` component.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from taktus.components.command.application.service import (
    CommissionDraft,
    PlanDialogue,
    PlanIncomplete,
    PlanningError,
    Unestimable,
)
from taktus.components.command.domain.model import AdministrationPart, Estimate, PlanDraft
from taktus.components.identity.domain.model import Right
from taktus.ports.identity import Resolution
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Tenant, UnitOfWork
from taktus.shared.v1 import (
    ExactnessClass,
    Fallback,
    LedgerRefs,
    Method,
    Plan,
    Rejected,
    Step,
)

CARRIED_OUT = "administration.carried_out"
UPDATE_COMMISSIONED = "instance.update_commissioned"
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
UPGRADING = "docs/guides/administration/upgrading.md"


@dataclass(frozen=True)
class DialogueAct:
    """An administrative act a plan may carry out: the arguments it takes, and the right the same
    act needs by hand."""

    needs: tuple[str, ...]
    right: Right = Right.ADMINISTER


IN_DIALOGUE: dict[str, DialogueAct] = {
    "identity.roles": DialogueAct(("identity", "roles")),
    "identity.revoke": DialogueAct(("link",)),
    "identity.grant": DialogueAct(("role", "right")),
    "identity.withdraw": DialogueAct(("role", "right")),
    "instance.update": DialogueAct(("to",)),
}
"""The acts a plan carries out, by the inventory's names (ADR-0296 §1)."""

BY_HAND_ONLY: dict[str, str] = {
    "tenant.list": "a read: it is answered, there is nothing to carry out",
    "tenant.create": "an act on the instance, which needs its administration key; an identity "
    "of a tenant never holds it, so a plan would need a wider right than by hand",
    "tenant.rename": "an act on the instance, which needs its administration key",
    "tenant.export": "an act on the instance, which needs its administration key; the export "
    "is a file handed to the holder of the key",
    "tenant.import": "an act on the instance, which needs its administration key",
    "identity.add": "it answers a key once; a key never passes through a plan's record",
    "identity.key": "it answers a key once; a key never passes through a plan's record",
    "identity.agent-key": "it answers a key once; a key never passes through a plan's record",
    "identity.links": "a read: it is answered, there is nothing to carry out",
    "identity.rights": "a read: it is answered, there is nothing to carry out",
    "units.show": "a read: it is answered, there is nothing to carry out",
    "units.set": "a unit's quota is a limit, which the limits' own dialogue sets (ADR-0282)",
    "units.clear": "a unit's quota is a limit, which the limits' own dialogue sets (ADR-0282)",
    "structure.show": "a read: it is answered, there is nothing to carry out",
    "structure.levels": "the structure is shaped in its own session, with structure.shape "
    "(ADR-0275)",
    "structure.unit": "the structure is shaped in its own session, with structure.shape",
    "structure.place": "the structure is shaped in its own session, with structure.shape",
    "structure.knowledge": "the structure is shaped in its own session, with structure.shape",
    "structure.where": "a read: it is answered, there is nothing to carry out",
    "project.create": "a project is the person's own, created in their session (ADR-0276)",
    "adapter.list": "a read: it is answered, there is nothing to carry out",
    "adapter.stop": "a stop acts at once on what runs; a plan due later would hold it back "
    "(ADR-0138)",
    "backup.list": "a read: it is answered, there is nothing to carry out",
    "instance.health": "a read: it is answered, there is nothing to carry out",
}
"""Every other act of the inventory, with why a plan does not carry it out (ADR-0296 §1)."""


class AdministrationRefused(PlanningError):
    """An administrative plan that cannot be commissioned, refused before anything is written."""

    def __init__(self, reason: str, message: str, findings: Sequence[str] = ()) -> None:
        self.reason = reason
        self.findings = tuple(findings)
        super().__init__(message if not findings else f"{message}: {'; '.join(findings)}")


class AdministeredIdentities(Protocol):
    """The identity component's acts a plan carries out, the same ones both ways in call."""

    async def holds(self, tenant: Tenant, identity: str, right: str) -> bool: ...

    async def identity(self, tenant: Tenant, identity: str) -> Resolution | None: ...

    async def set_roles(
        self, tenant: Tenant, identity: str, roles: Sequence[str], *, by: str | None = None
    ) -> Any: ...

    async def links(self, tenant: Tenant) -> Sequence[Any]: ...

    async def revoke(self, tenant: Tenant, link: str, *, by: str | None = None) -> Any: ...

    async def grant(
        self, tenant: Tenant, role: str, right: Right, *, by: str | None = None
    ) -> Any: ...

    async def withdraw(
        self, tenant: Tenant, role: str, right: Right, *, by: str | None = None
    ) -> Any: ...


def part_of(act: str, arguments: Mapping[str, Any] | None = None) -> AdministrationPart:
    """The act as a draft carries it; refused for an act no plan carries out."""
    chosen = IN_DIALOGUE.get(act)
    if chosen is None:
        why = BY_HAND_ONLY.get(act)
        if why is None:
            raise PlanningError(f"there is no administrative act {act!r}")
        raise PlanningError(f"{act} is not carried out as a plan: {why}")
    given = {str(k): str(v).strip() for k, v in (arguments or {}).items()}
    unknown = sorted(set(given) - set(chosen.needs))
    if unknown:
        raise PlanningError(f"{act} takes {', '.join(chosen.needs)}, not {', '.join(unknown)}")
    return AdministrationPart(act=act, arguments=given, needs=chosen.needs)


def steps_of(act: str) -> tuple[tuple[Step, ...], tuple[Estimate, ...]]:
    """The steps the act is carried out by, with their estimates: what choosing it sets."""
    if act == "instance.update":
        return _update_steps()
    step = Step(
        id="act",
        method=Method.RULE,
        reason=f"{act} is carried out by the use case the command line and the web app call "
        "for it, with the identity that commissioned the plan as its actor",
        rejected=(
            Rejected(
                method=Method.LLM,
                why="an administrative act changes who may do what; it is never a value a "
                "language model produces",
            ),
            Rejected(
                method=Method.HUMAN,
                why="a person commissions the plan; carrying it out by hand again adds nothing",
            ),
        ),
        exactness=ExactnessClass.EXACT,
    )
    estimate = Estimate(
        step_id="act", figure=1, unit="seconds", basis="one call of the act's use case"
    )
    return (step,), (estimate,)


def _update_steps() -> tuple[tuple[Step, ...], tuple[Estimate, ...]]:
    """An update of Taktus as a person carries it out, from the upgrading guide (ADR-0124)."""
    not_taktus = Rejected(
        method=Method.WORKER,
        why="no instance administers the platform it runs on (ADR-0025), and a version Taktus "
        "built is put into production by a person or another instance (ADR-0013 D)",
    )
    steps = (
        Step(
            id="backup",
            method=Method.HUMAN,
            reason=f"a backup, moved off the machine, is the way back ({UPGRADING}, section 1)",
            rejected=(not_taktus,),
        ),
        Step(
            id="upgrade",
            method=Method.HUMAN,
            reason=f"the release named, installed one release at a time ({UPGRADING}, sections "
            "2 and 3)",
            rejected=(not_taktus,),
            fallback=Fallback(
                when="the upgrade fails",
                to=Method.HUMAN,
            ),
            depends_on=("backup",),
        ),
        Step(
            id="check",
            method=Method.HUMAN,
            reason=f"the instance answers that it is ready and every tenant's ledger verifies "
            f"({UPGRADING}, section 4); otherwise the previous release is brought back from "
            "the backup, without Taktus (section 5)",
            rejected=(not_taktus,),
            depends_on=("upgrade",),
        ),
    )
    estimates = tuple(
        Estimate(step_id=s, figure=f, unit="seconds", basis=b)
        for s, f, b in (
            ("backup", 900, "the upgrading guide's backup, by a person; not measured here"),
            ("upgrade", 600, "the release's image pulled and started; not measured here"),
            ("check", 300, "two commands of the upgrading guide, by a person"),
        )
    )
    return steps, estimates


def _digest(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AdministrationPlans:
    def __init__(
        self,
        identities: AdministeredIdentities,
        dialogue: PlanDialogue,
        ledger: Ledger,
        work: UnitOfWork,
    ) -> None:
        self._identities = identities
        self._dialogue = dialogue
        self._ledger = ledger
        self._work = work

    async def commission(self, tenant: Tenant, identity: str, draft: PlanDraft) -> Plan:
        """The draft's plan commissioned by `identity`, and its act carried out; refused,
        writing nothing, where either would be."""
        part = draft.administration
        if part is None:
            raise PlanningError("this draft carries no administrative act")
        missing = draft.missing()
        if missing:
            raise PlanIncomplete(missing)
        unestimable = draft.unestimable()
        if unestimable:
            raise Unestimable(unestimable)
        chosen = IN_DIALOGUE.get(part.act)
        if chosen is None:
            raise PlanningError(f"{part.act} is not carried out as a plan")
        if not await self._identities.holds(tenant, identity, chosen.right.value):
            raise AdministrationRefused(
                "right",
                f"{part.act} needs a role holding {chosen.right.value}, as it does by hand",
            )
        await self._checked(tenant, part)
        plan = await self._dialogue.commission(
            CommissionDraft(draft_id=draft.id, tenant=tenant, by=identity)
        )
        await self._record(tenant, plan.id, identity, part)
        await self._carried_out(tenant, identity, part)
        return plan

    async def _checked(self, tenant: Tenant, part: AdministrationPart) -> None:
        """The act's target exists and its arguments hold, before anything is written."""
        given = part.arguments
        if part.act == "identity.roles":
            if await self._identities.identity(tenant, given["identity"]) is None:
                raise AdministrationRefused(
                    "target", f"the tenant has no identity {given['identity']!r}"
                )
        elif part.act == "identity.revoke":
            active = {link.id for link in await self._identities.links(tenant) if link.active}
            if given["link"] not in active:
                raise AdministrationRefused("target", f"no active channel link {given['link']!r}")
        elif part.act in ("identity.grant", "identity.withdraw"):
            try:
                Right(given["right"])
            except ValueError as error:
                raise AdministrationRefused(
                    "target", f"there is no right {given['right']!r}"
                ) from error
        elif part.act == "instance.update" and VERSION.match(given["to"]) is None:
            raise AdministrationRefused(
                "target", f"{given['to']!r} is no release; a release is named as 1.0.1"
            )

    async def _record(
        self, tenant: Tenant, plan_id: str, identity: str, part: AdministrationPart
    ) -> None:
        kind = UPDATE_COMMISSIONED if part.act == "instance.update" else CARRIED_OUT
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=kind,
                    refs=LedgerRefs(tenant=tenant, plan_id=plan_id, actor=identity),
                    outcome="commissioned" if kind == UPDATE_COMMISSIONED else "carried_out",
                    content_digest=_digest({"act": part.act, "arguments": part.arguments}),
                ),
            )

    async def _carried_out(self, tenant: Tenant, by: str, part: AdministrationPart) -> None:
        given = part.arguments
        if part.act == "identity.roles":
            said = given["roles"].strip()
            roles = [] if said == "none" else [r.strip() for r in said.split(",") if r.strip()]
            await self._identities.set_roles(tenant, given["identity"], roles, by=by)
        elif part.act == "identity.revoke":
            await self._identities.revoke(tenant, given["link"], by=by)
        elif part.act == "identity.grant":
            await self._identities.grant(tenant, given["role"], Right(given["right"]), by=by)
        elif part.act == "identity.withdraw":
            await self._identities.withdraw(tenant, given["role"], Right(given["right"]), by=by)
        # instance.update: nothing is applied here; a person carries out the steps (ADR-0013 D).
