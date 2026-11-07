"""Use case: an organisation instantiates a domain blueprint in dialogue (ADR-0263, UC-15.1).

`DomainInstances` is the one writer of `DomainInstance`. It starts an instance from an admitted
blueprint, takes the answers to its questions — a tool per capability, the processes left out,
the owner — and, once no question is open, makes each kept process a proposal at level 2 or
below. A later version of the blueprint is offered: each changed bundle becomes a proposal,
nothing is applied, and the instance keeps the version it was instantiated from.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from taktus.components.catalog.domain.model.blueprint import (
    Admitted,
    Binding,
    DomainBlueprint,
    DomainInstance,
    Offer,
    ProposedProcess,
    Question,
)
from taktus.components.catalog.domain.service import blueprints as rules
from taktus.components.catalog.ports.domains import Adapters, People, ProcessProposals, Refused
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.persistence import Repository, Tenant, UnitOfWork


class DomainRefused(Exception):
    """An act on an instance that is not taken, with why. `kind`: `unknown` — no such instance
    or blueprint; `open` — a question is still open; `refused` — the answer or proposal is not
    one the instance takes."""

    def __init__(self, kind: str, detail: str, questions: Sequence[Question] = ()) -> None:
        self.kind = kind
        self.questions = tuple(questions)
        super().__init__(detail)


class DomainInstances:
    def __init__(
        self,
        instances: Repository[DomainInstance],
        work: UnitOfWork,
        proposals: ProcessProposals,
        people: People,
        adapters: Adapters,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._instances = instances
        self._work = work
        self._proposals = proposals
        self._people = people
        self._adapters = adapters
        self._clock = clock
        self._ids = ids

    async def start(self, tenant: Tenant, admitted: Admitted, by: str) -> DomainInstance:
        blueprint = admitted.blueprint
        instance = DomainInstance(
            id=self._ids.new("dom"),
            tenant=tenant,
            created_at=self._clock.now(),
            blueprint=blueprint.id,
            blueprint_version=blueprint.version,
            domain=blueprint.domain,
            started_by=by,
        )
        async with self._work.transaction(tenant):
            await self._instances.put(tenant, instance)
        return instance

    async def get(self, tenant: Tenant, instance_id: str) -> DomainInstance:
        async with self._work.transaction(tenant):
            found = await self._instances.get(tenant, instance_id)
        if found is None:
            raise DomainRefused("unknown", f"no domain instance {instance_id!r}")
        return found

    async def listed(self, tenant: Tenant) -> list[DomainInstance]:
        async with self._work.transaction(tenant):
            return list(await self._instances.list(tenant))

    def questions(self, admitted: Admitted, instance: DomainInstance) -> tuple[Question, ...]:
        blueprint = self._same(admitted, instance)
        options = {c: self._adapters.declaring(c) for c in blueprint.connectors}
        return rules.questions(blueprint, instance, options)

    async def answer(
        self,
        tenant: Tenant,
        admitted: Admitted,
        instance_id: str,
        capability: str,
        adapter: str | None,
        by: str,
    ) -> DomainInstance:
        """The capability answered: with an adapter that declares it, or None for none."""
        instance = await self.get(tenant, instance_id)
        blueprint = self._same(admitted, instance)
        refusal = rules.answer_refusal(
            blueprint, capability, adapter, self._adapters.declaring(capability)
        )
        if refusal is not None:
            raise DomainRefused("refused", refusal)
        binding = Binding(capability=capability, adapter=adapter, by=by, at=self._clock.now())
        kept = tuple(b for b in instance.bindings if b.capability != capability)
        return await self._put(tenant, instance.model_copy(update={"bindings": (*kept, binding)}))

    async def leave_out(
        self, tenant: Tenant, admitted: Admitted, instance_id: str, processes: Iterable[str]
    ) -> DomainInstance:
        instance = await self.get(tenant, instance_id)
        blueprint = self._same(admitted, instance)
        named = tuple(processes)
        refusal = rules.leave_out_refusal(blueprint, named)
        if refusal is not None:
            raise DomainRefused("refused", refusal)
        left = tuple(dict.fromkeys((*instance.left_out, *named)))
        return await self._put(tenant, instance.model_copy(update={"left_out": left}))

    async def name_owner(self, tenant: Tenant, instance_id: str, owner: str) -> DomainInstance:
        """The domain's one owner, an identity the tenant knows (UC-15.5)."""
        instance = await self.get(tenant, instance_id)
        if not await self._people.known(tenant, owner):
            raise DomainRefused("refused", f"{owner} is not an identity of the tenant {tenant}")
        return await self._put(tenant, instance.model_copy(update={"owner": owner}))

    async def propose(
        self, tenant: Tenant, admitted: Admitted, instance_id: str, by: str
    ) -> DomainInstance:
        """Every kept process with a bundle, not yet proposed, as a proposal at level 2 or
        below. Refused while a question is open: the owner's first among them."""
        instance = await self.get(tenant, instance_id)
        blueprint = self._same(admitted, instance)
        open_questions = self.questions(admitted, instance)
        if open_questions:
            raise DomainRefused(
                "open",
                "nothing is proposed while a question is open: "
                + "; ".join(q.asks for q in open_questions),
                open_questions,
            )
        made: list[ProposedProcess] = []
        for process in blueprint.processes:
            bundle = admitted.bundles.get(process.id)
            if (
                bundle is None
                or process.process is None
                or process.id in instance.left_out
                or instance.proposal_of(process.id) is not None
            ):
                continue
            made.append(await self._proposed(tenant, admitted, process.id, by, instance))
        return await self._put(
            tenant, instance.model_copy(update={"proposed": (*instance.proposed, *made)})
        )

    async def offer(self, tenant: Tenant, later: Admitted, instance_id: str, by: str) -> Offer:
        """A later version of the blueprint, offered: each process the instance proposed whose
        bundle changed becomes a proposal. Nothing is applied; the instance keeps its version."""
        instance = await self.get(tenant, instance_id)
        blueprint = later.blueprint
        if blueprint.id != instance.blueprint:
            raise DomainRefused(
                "unknown",
                f"{instance_id} is an instance of {instance.blueprint}, not {blueprint.id}",
            )
        made: list[ProposedProcess] = []
        new: list[str] = []
        for process in blueprint.processes:
            bundle = later.bundles.get(process.id)
            if bundle is None or process.id in instance.left_out:
                continue
            before = instance.proposal_of(process.id)
            if before is None:
                new.append(process.id)
                continue
            if before.digest == bundle.digest:
                continue
            made.append(await self._proposed(tenant, later, process.id, by, instance))
        await self._put(
            tenant, instance.model_copy(update={"proposed": (*instance.proposed, *made)})
        )
        return Offer(
            instance=instance.id,
            blueprint_version=blueprint.version,
            proposed=tuple(made),
            new=tuple(new),
        )

    async def _proposed(
        self,
        tenant: Tenant,
        admitted: Admitted,
        process_id: str,
        by: str,
        instance: DomainInstance,
    ) -> ProposedProcess:
        blueprint = admitted.blueprint
        process = blueprint.process(process_id)
        bundle = admitted.bundles[process_id]
        if process is None or process.process is None:
            raise DomainRefused("unknown", f"the blueprint has no bundle for {process_id}")
        changed = rules.starting(bundle.content, process, blueprint)
        try:
            proposal, version = await self._proposals.propose(
                tenant,
                process.process,
                changed,
                by,
                f"from the domain blueprint {blueprint.id} {blueprint.version}, "
                f"instance {instance.id}",
            )
        except Refused as error:
            raise DomainRefused(
                "refused", f"{process_id} is not proposed: {'; '.join(error.findings)}"
            ) from error
        return ProposedProcess(
            process=process_id,
            process_id=process.process,
            version=version,
            proposal=proposal,
            level=rules.start_level(process.level),
            digest=bundle.digest,
            blueprint_version=blueprint.version,
        )

    def _same(self, admitted: Admitted, instance: DomainInstance) -> DomainBlueprint:
        blueprint = admitted.blueprint
        if blueprint.id != instance.blueprint:
            raise DomainRefused(
                "unknown",
                f"{instance.id} is an instance of {instance.blueprint}, not {blueprint.id}",
            )
        return blueprint

    async def _put(self, tenant: Tenant, instance: DomainInstance) -> DomainInstance:
        async with self._work.transaction(tenant):
            await self._instances.put(tenant, instance)
        return instance
