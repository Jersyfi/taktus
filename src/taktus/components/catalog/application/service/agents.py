"""Use case: a shared agent's core and its role profiles, versioned apart (ADR-0163, UC-8.11).

- **A core version is held** until every active profile narrows it and every profile's
  evaluation on it passed; then it becomes the agent's active core, and the one before is
  superseded. The first core of an agent, with no profile yet, is active at once.
- **A profile only narrows.** A profile that grants more than the active core is refused and
  recorded as `agent.profile_refused`, outcome `widens`.
- **A call is resolved to a profile** from the caller's roles and recorded as `agent.called`
  with the profile and how it was found. Nothing here measures a person: use and cost are
  counted by profile, and a profile is a role (principle 14).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from taktus.components.catalog.domain.model.agent import (
    AgentCore,
    AgentError,
    CoreState,
    Grants,
    RoleProfile,
    profile_id,
    widening,
)
from taktus.components.catalog.domain.service import agents
from taktus.components.catalog.domain.service.agents import Found
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import AutonomyLevel, LedgerRefs

CORE_PROPOSED = "agent.core_proposed"
CORE_HELD = "agent.core_held"
CORE_ACTIVATED = "agent.core_activated"
PROFILE_SET = "agent.profile_set"
PROFILE_REFUSED = "agent.profile_refused"
CALLED = "agent.called"


class AgentCatalog:
    def __init__(
        self,
        cores: Repository[AgentCore],
        profiles: Repository[RoleProfile],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
    ) -> None:
        self._cores = cores
        self._profiles = profiles
        self._work = work
        self._ledger = ledger
        self._clock = clock

    # --- reading ----------------------------------------------------------------------------

    async def cores(self, tenant: Tenant, agent: str) -> list[AgentCore]:
        async with self._work.transaction(tenant):
            found = await self._cores.list(tenant)
        return sorted((c for c in found if c.agent == agent), key=lambda c: c.proposed_at)

    async def active_core(self, tenant: Tenant, agent: str) -> AgentCore | None:
        return next(
            (c for c in await self.cores(tenant, agent) if c.state is CoreState.ACTIVE), None
        )

    async def profiles(
        self, tenant: Tenant, agent: str, *, every: bool = False
    ) -> list[RoleProfile]:
        async with self._work.transaction(tenant):
            found = await self._profiles.list(tenant)
        return sorted(
            (p for p in found if p.agent == agent and (every or p.active)),
            key=lambda p: (p.role, p.set_at),
        )

    async def brief(self, tenant: Tenant, profile: str) -> str | None:
        """What a run serving the profile hands its steps: its core's instructions, then what
        the role's profile sets. `profile` is `<agent>:<role>@<version>`, served under the
        active core, or `<agent>@<core>/<agent>:<role>@<version>`, under that core — the
        proposed side of a profile's evaluation (ADR-0163 §4). None for one the catalogue does
        not hold."""
        core_id, _, profile_ref = profile.rpartition("/")
        async with self._work.transaction(tenant):
            found = await self._profiles.get(tenant, profile_ref)
            core = None
            if found is not None and core_id:
                core = await self._cores.get(tenant, core_id)
            elif found is not None:
                core = next(
                    (
                        c
                        for c in await self._cores.list(tenant)
                        if c.agent == found.agent and c.state is CoreState.ACTIVE
                    ),
                    None,
                )
        if found is None or core is None or core.agent != found.agent:
            return None
        return found.brief(core)

    async def diagram(self, tenant: Tenant, agent: str) -> str:
        core = await self.active_core(tenant, agent)
        if core is None:
            raise AgentError("unknown", f"the agent {agent!r} has no active core")
        return agents.diagram(core, await self.profiles(tenant, agent))

    # --- the core ---------------------------------------------------------------------------

    async def propose_core(
        self,
        tenant: Tenant,
        *,
        agent: str,
        version: str,
        purpose: str,
        instructions: str,
        flow: str,
        autonomy_level: AutonomyLevel,
        grants: Grants,
        model: str | None = None,
        by: str | None = None,
    ) -> AgentCore:
        """A new core version, held until every profile's evaluation passed on it; active at
        once while the agent has no profile."""
        core_id = f"{agent}@{version}"
        async with self._work.transaction(tenant):
            if await self._cores.get(tenant, core_id) is not None:
                raise AgentError("exists", f"{core_id} exists, and a core version never changes")
            core = AgentCore(
                id=core_id,
                tenant=tenant,
                agent=agent,
                version=version,
                purpose=purpose,
                instructions=instructions,
                flow=flow,
                model=model,
                autonomy_level=autonomy_level,
                grants=grants,
                proposed_at=self._clock.now(),
            )
            await self._cores.put(tenant, core)
            await self._record(tenant, CORE_PROPOSED, core_id, "proposed", actor=by)
        return await self.activate(tenant, core_id)

    async def record_verdict(
        self, tenant: Tenant, core_id: str, profile: str, verdict: str
    ) -> AgentCore:
        """One profile's evaluation verdict on a held core, then the core activated if it now
        may be."""
        async with self._work.transaction(tenant):
            core = await self._cores.get(tenant, core_id)
            if core is None:
                raise AgentError("unknown", f"no core {core_id!r}")
            changed = core.model_copy(update={"verdicts": {**core.verdicts, profile: verdict}})
            await self._cores.put(tenant, changed)
        return await self.activate(tenant, core_id)

    async def activate(self, tenant: Tenant, core_id: str) -> AgentCore:
        """The core active when nothing holds it; held, and `agent.core_held` recorded once
        every profile has a verdict and one did not pass or a profile would widen it."""
        async with self._work.transaction(tenant):
            core = await self._cores.get(tenant, core_id)
            if core is None:
                raise AgentError("unknown", f"no core {core_id!r}")
            if core.state is not CoreState.HELD:
                return core
            profiles = [
                p for p in await self._profiles.list(tenant) if p.agent == core.agent and p.active
            ]
            findings = agents.held(core, profiles)
            if findings:
                complete = all(p.id in core.verdicts for p in profiles)
                if complete:
                    await self._record(tenant, CORE_HELD, core_id, "held")
                return core
            for other in await self._cores.list(tenant):
                if other.agent == core.agent and other.state is CoreState.ACTIVE:
                    await self._cores.put(
                        tenant, other.model_copy(update={"state": CoreState.SUPERSEDED})
                    )
            active = core.model_copy(update={"state": CoreState.ACTIVE})
            await self._cores.put(tenant, active)
            await self._record(tenant, CORE_ACTIVATED, core_id, "activated")
        return active

    async def held_because(self, tenant: Tenant, core_id: str) -> list[str]:
        async with self._work.transaction(tenant):
            core = await self._cores.get(tenant, core_id)
        if core is None:
            raise AgentError("unknown", f"no core {core_id!r}")
        return agents.held(core, await self.profiles(tenant, core.agent))

    # --- profiles ---------------------------------------------------------------------------

    async def set_profile(
        self,
        tenant: Tenant,
        *,
        agent: str,
        role: str,
        version: str,
        grants: Grants,
        vocabulary: Sequence[str] = (),
        tone: str | None = None,
        by: str | None = None,
    ) -> RoleProfile:
        """A role's profile against the active core. One that grants more is refused."""
        core = await self.active_core(tenant, agent)
        if core is None:
            raise AgentError("unknown", f"the agent {agent!r} has no active core")
        identifier = profile_id(agent, role, version)
        wider = widening(grants, core.grants)
        if wider:
            async with self._work.transaction(tenant):
                await self._record(tenant, PROFILE_REFUSED, identifier, "widens", actor=by)
            raise AgentError(
                "widens", f"{identifier} would grant more than {core.id}", tuple(wider)
            )
        profile = RoleProfile(
            id=identifier,
            tenant=tenant,
            agent=agent,
            role=role,
            version=version,
            grants=grants,
            vocabulary=tuple(vocabulary),
            tone=tone,
            set_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            if await self._profiles.get(tenant, identifier) is not None:
                raise AgentError(
                    "exists", f"{identifier} exists, and a profile version never changes"
                )
            for other in await self._profiles.list(tenant):
                if other.agent == agent and other.role == role and other.active:
                    await self._profiles.put(tenant, other.model_copy(update={"active": False}))
            await self._profiles.put(tenant, profile)
            await self._record(tenant, PROFILE_SET, identifier, "set", actor=by)
        return profile

    # --- calls ------------------------------------------------------------------------------

    async def resolve(
        self, tenant: Tenant, agent: str, roles: Collection[str], chosen: str | None = None
    ) -> tuple[AgentCore, RoleProfile, Found]:
        core = await self.active_core(tenant, agent)
        if core is None:
            raise AgentError("unknown", f"the agent {agent!r} has no active core")
        profile, found = agents.resolve(await self.profiles(tenant, agent), roles, chosen)
        return core, profile, found

    async def called(
        self, tenant: Tenant, profile: RoleProfile, found: Found, *, run_id: str, by: str
    ) -> None:
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=CALLED,
                    refs=LedgerRefs(tenant=tenant, agent_id=profile.id, run_id=run_id, actor=by),
                    outcome=found,
                ),
            )

    async def _record(
        self, tenant: Tenant, kind: str, agent_id: str, outcome: str, *, actor: str | None = None
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(tenant=tenant, agent_id=agent_id, actor=actor),
                outcome=outcome,
            ),
        )
