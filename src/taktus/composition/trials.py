"""A model tried on fixed cases before it is introduced, proposed or changed (#448, ADR-0149).

- **Start.** A person names a purpose and one or more candidates, each a model the instance's
  configuration holds (`model.<member>`). The cases are the evaluation cases of every process
  whose active version has a step on a language model of that purpose (ADR-0134 §1). Each case
  runs once per candidate, as a rehearsal (ADR-0030), with the purpose bound to the candidate
  for that run alone (`Run.bindings`). Every run goes the one path every run takes: a command,
  a commissioned plan, a run submitted to the queue. The trial is a document in the object
  store; the ledger records `trial.started` with its digest, by the person, and the occasion as
  outcome.
- **Report.** Read from the ledger by `TrialReports` (ADR-0149 §2): per candidate the cases
  passed, money, tokens in and out, wall time, each case's results beside the others'.
- **Named cases.** A person may name cases beside the evaluation cases: a process that asks for
  the purpose and the inputs of one run. Each runs on the process's active version, once per
  candidate, as the evaluation cases do; it has no target, so it passes on its run's ending.
- **Decline.** A person may decline an offer (`trial.declined`). The offer is not shown again
  until its occasion arises anew: a model proposed again, or a version that changed again.
- **Offer.** A trial is offered, never started on its own (ADR-0149 §3): when a purpose's first
  model has never answered a step of the tenant and no trial included it (`introduced`); when
  Taktus proposed another model for a purpose (`proposed`, the ledger's `trial.offered`); and
  when the model the provider reports for a member's steps changed its version since the last
  trial of the purpose (`changed`). The offers are computed when they are read: nothing is
  stored but what Taktus proposed.

The choice of a model stays a person's act (M3.12, M3.14): nothing here binds a model to a
purpose beyond one case run. Who started a trial is kept to say whose act it was; no measure is
computed from it (principle 14). This is wiring, because each act crosses the process, command,
run and accounting components.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from taktus.components.accounting.application.service import (
    OCCASIONS,
    NamedCase,
    Offer,
    ReportTrial,
    Trial,
    TrialCase,
    TrialError,
    TrialRead,
    TrialReports,
)
from taktus.components.command.application.service import CommissionPlan, CommissionPlanHandler
from taktus.components.process.domain.model import Process, ProcessVersion
from taktus.components.run.application.service import RunEngine, StartRun
from taktus.components.run.domain.model import LlmWork, Run, RunError, parse_work
from taktus.composition.evaluations import Evaluations, settled
from taktus.ports.clock import Clock, Identifiers
from taktus.ports.identity import IdentityResolver
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.model import ResolvedModel
from taktus.ports.objectstore import ObjectStore
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.ports.worker import Limits
from taktus.shared.v1 import Command, Intent, LedgerEntry, LedgerRefs, ReplyTo

CHANNEL = "channel.web"
STARTED = "trial.started"
OFFERED = "trial.offered"
"""Taktus proposed another model for a purpose: the occasion `proposed` (ADR-0149 §3)."""
DECLINED = "trial.declined"
"""A person declined an offer: it stands no longer until its occasion arises anew."""
DECLINABLE = ("introduced", "proposed", "changed")
MAX_NAMED = 50
"""The most cases a person may name for one trial: each runs once per candidate."""
STEP_FINISHED = "step.finished"


class Models(Protocol):
    """The instance's configured models, as a trial reads them."""

    async def chain(self, purpose: str) -> list[ResolvedModel]: ...

    async def bound(self, adapter: str) -> ResolvedModel | None: ...

    def members(self) -> list[tuple[str, tuple[str, ...], str | None]]: ...


class Trials:
    def __init__(
        self,
        *,
        processes: Repository[Process],
        versions: Repository[ProcessVersion],
        runs: Repository[Run],
        evaluations: Evaluations,
        commission: CommissionPlanHandler,
        engine: RunEngine,
        identities: IdentityResolver,
        models: Models,
        reports: TrialReports,
        ledger: Ledger,
        objects: ObjectStore,
        work: UnitOfWork,
        clock: Clock,
        ids: Identifiers,
    ) -> None:
        self._processes = processes
        self._versions = versions
        self._runs = runs
        self._evaluations = evaluations
        self._commission = commission
        self._engine = engine
        self._identities = identities
        self._models = models
        self._reports = reports
        self._ledger = ledger
        self._objects = objects
        self._work = work
        self._clock = clock
        self._ids = ids

    # --- starting --------------------------------------------------------------------------

    async def start(
        self,
        tenant: Tenant,
        purpose: str,
        candidates: Sequence[str],
        by: str,
        occasion: str = "asked",
        own: Sequence[NamedCase] = (),
    ) -> Trial:
        """The trial, its runs submitted: each case of the purpose once per candidate, the
        evaluation cases and the cases the person named."""
        if occasion not in OCCASIONS:
            raise TrialError("invalid", f"{occasion!r} is not an occasion: {', '.join(OCCASIONS)}")
        named = list(dict.fromkeys(candidates))
        if not named:
            raise TrialError("invalid", "a trial needs at least one candidate model")
        for candidate in named:
            if await self._models.bound(candidate) is None:
                raise TrialError("invalid", f"{candidate!r} is no model of this instance")
        placed = await self._identities.identity(tenant, by)
        if placed is None:
            raise TrialError("unknown", f"the identity {by!r} is not known to {tenant!r}")
        if len(own) > MAX_NAMED:
            raise TrialError("invalid", f"a trial names at most {MAX_NAMED} cases of its own")
        cases, versions, left_out = await self._cases(tenant, purpose)
        cases += await self._named(tenant, purpose, own, versions)
        if not cases:
            raise TrialError(
                "empty",
                f"no process of this tenant has a step of purpose {purpose!r} with evaluation "
                "cases to run",
            )
        trial = Trial(
            id=self._ids.new("trl"),
            purpose=purpose,
            candidates=tuple(named),
            occasion=occasion,
            started_at=self._clock.now(),
            cases=tuple(case for case, _ in cases),
            left_out=left_out,
        )
        runs: dict[str, dict[str, str]] = {}
        for index, candidate in enumerate(named):
            of_candidate: dict[str, str] = {}
            for number, (case, inputs) in enumerate(cases):
                version = versions[case.process_version]
                run = await self._submit(
                    tenant,
                    trial,
                    placed.identity,
                    placed.org_path,
                    run_id=f"{trial.id}-{index}-{number}",
                    version=version,
                    case_id=case.case,
                    inputs=inputs,
                    candidate=candidate,
                )
                of_candidate[case.key] = run.id
            runs[candidate] = of_candidate
        trial = trial.model_copy(update={"runs": runs})
        digest = await self._objects.put(_canonical(trial.document()))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=STARTED,
                    refs=LedgerRefs(tenant=tenant, actor=placed.identity),
                    outcome=occasion,
                    content_digest=digest,
                ),
            )
        return trial

    async def _named(
        self,
        tenant: Tenant,
        purpose: str,
        named: Sequence[NamedCase],
        versions: dict[str, ProcessVersion],
    ) -> list[tuple[TrialCase, Mapping[str, Any]]]:
        """The cases a person named, each on its process's active version, which must ask for
        the purpose and name its limits; `versions` gains every version they run on. A case
        that cannot run is refused before any run starts, naming why."""
        if not named:
            return []
        asking = {v.process_id: v for v in await self._asking(tenant, purpose)}
        found: list[tuple[TrialCase, Mapping[str, Any]]] = []
        for number, case in enumerate(named, 1):
            version = asking.get(case.process)
            if version is None:
                raise TrialError(
                    "invalid",
                    f"case {number}: {case.process!r} is no active process of this tenant that "
                    f"asks for {purpose!r}",
                )
            if version.limits is None:
                raise TrialError(
                    "invalid",
                    f"case {number}: {version.ref} names no `limits`; a rehearsal needs a budget",
                )
            versions[version.ref] = version
            case_id = f"named-{number}"
            key = f"{version.process_id}/{case_id}"
            found.append(
                (
                    TrialCase(key=key, process_version=version.ref, case=case_id, named=True),
                    dict(case.inputs),
                )
            )
        return found

    async def _cases(
        self, tenant: Tenant, purpose: str
    ) -> tuple[
        list[tuple[TrialCase, Mapping[str, Any]]], dict[str, ProcessVersion], dict[str, str]
    ]:
        """The evaluation cases of every active version that asks for the purpose, in the order
        of the processes' identifiers, each with its inputs; and the cases left out, with why."""
        cases: list[tuple[TrialCase, Mapping[str, Any]]] = []
        versions: dict[str, ProcessVersion] = {}
        left_out: dict[str, str] = {}
        for version in await self._asking(tenant, purpose):
            versions[version.ref] = version
            evaluated, excluded = await self._evaluations.evaluation_set(tenant, version)
            for case_id, why in sorted(excluded.items()):
                left_out[f"{version.process_id}/{case_id}"] = why
            if version.limits is None:
                for case in evaluated:
                    left_out[f"{version.process_id}/{case.id}"] = (
                        f"{version.ref} names no `limits`; a rehearsal needs a budget"
                    )
                continue
            for case in evaluated:
                key = f"{version.process_id}/{case.id}"
                trial_case = TrialCase(key=key, process_version=version.ref, case=case.id)
                cases.append((trial_case, case.inputs))
        return cases, versions, left_out

    async def _asking(self, tenant: Tenant, purpose: str) -> list[ProcessVersion]:
        """The active versions with a step on a language model of the purpose."""
        async with self._work.transaction(tenant):
            processes = sorted(await self._processes.list(tenant), key=lambda p: p.id)
            actives = [
                await self._versions.get(tenant, f"{p.id}@{p.active_version}")
                for p in processes
                if p.active_version is not None
            ]
        return [v for v in actives if v is not None and purpose in _purposes(v)]

    async def _submit(
        self,
        tenant: Tenant,
        trial: Trial,
        by: str,
        org_path: Sequence[str],
        *,
        run_id: str,
        version: ProcessVersion,
        case_id: str,
        inputs: Mapping[str, Any],
        candidate: str,
    ) -> Run:
        """One case run on one candidate, through the one path every run takes. Its identifier
        is derived from the trial, so that a second submission names the same run."""
        async with self._work.transaction(tenant):
            existing = await self._runs.get(tenant, run_id)
        if existing is not None:
            return existing
        goal = f"try {candidate} for {trial.purpose} on the case {case_id} of {version.ref}"
        command = Command(
            id=self._ids.new("cmd"),
            channel=CHANNEL,
            identity=by,
            org_path=tuple(org_path),
            intent=Intent(raw=goal, recognised="model.trial"),
            context={"inputs": dict(inputs), "trial": trial.id},
            reply_to=ReplyTo(channel=CHANNEL, address="ledger"),
            received_at=self._clock.now(),
        )
        plan = await self._commission.execute(
            CommissionPlan(
                command=command,
                tenant=tenant,
                goal=goal,
                autonomy_level=version.autonomy_level,
                steps=version.ordered(),
            )
        )
        return await self._engine.submit(
            StartRun(
                org_unit=command.org_unit,
                plan=plan,
                work={k: dict(v) for k, v in version.work.items()},
                budget=Limits.model_validate(dict(version.limits or {})),
                process_version=version.ref,
                actor=by,
                tenant=tenant,
                inputs=dict(inputs),
                rehearsal=True,
                run_id=run_id,
                actions=dict(version.autonomy.action_levels),
                bindings={trial.purpose: candidate},
            )
        )

    # --- reading ---------------------------------------------------------------------------

    async def of_tenant(self, tenant: Tenant) -> list[Trial]:
        """Every trial of the tenant, newest first."""
        async with self._work.transaction(tenant):
            started = await self._ledger.of_kinds(tenant, {STARTED})
        trials = [await self._document(entry) for entry in started]
        return sorted(
            (t for t in trials if t is not None), key=lambda t: t.started_at, reverse=True
        )

    async def read(self, tenant: Tenant, trial_id: str) -> TrialRead:
        """One trial with its report, read from the ledger now."""
        found = next((t for t in await self.of_tenant(tenant) if t.id == trial_id), None)
        if found is None:
            raise TrialError("unknown", f"no trial {trial_id!r}")
        report = await self._reports.execute(
            ReportTrial(purpose=found.purpose, tenant=tenant, runs=found.runs)
        )
        async with self._work.transaction(tenant):
            runs = [
                await self._runs.get(tenant, run_id)
                for cases in found.runs.values()
                for run_id in cases.values()
            ]
        return TrialRead(trial=found, report=report, settled=all(settled(r) for r in runs))

    async def _document(self, entry: LedgerEntry) -> Trial | None:
        if entry.content_digest is None:
            return None
        content = await self._objects.get(entry.content_digest)
        return None if content is None else Trial.model_validate(json.loads(content))

    # --- offering --------------------------------------------------------------------------

    async def propose(self, tenant: Tenant, purpose: str, candidate: str, reason: str) -> None:
        """Taktus proposes another model for a purpose: a trial is offered for it (ADR-0149
        §3). The proposal is recorded, never acted on."""
        if await self._models.bound(candidate) is None:
            raise TrialError("invalid", f"{candidate!r} is no model of this instance")
        document = {"purpose": purpose, "candidate": candidate, "reason": reason}
        digest = await self._objects.put(_canonical(document))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=OFFERED,
                    refs=LedgerRefs(tenant=tenant),
                    outcome="proposed",
                    content_digest=digest,
                ),
            )

    async def decline(
        self, tenant: Tenant, purpose: str, occasion: str, model: str, by: str, reason: str
    ) -> None:
        """A person declines an offer: it is not offered again until its occasion arises anew —
        a model proposed again after the decline, or a version that changed after it. The
        decline is the person's act, recorded with them as its actor; nothing is bound."""
        if occasion not in DECLINABLE:
            raise TrialError(
                "invalid", f"{occasion!r} is no occasion an offer has: {', '.join(DECLINABLE)}"
            )
        standing = [
            o
            for o in await self.offers(tenant)
            if (o.purpose, o.occasion, o.model) == (purpose, occasion, model)
        ]
        if not standing:
            raise TrialError(
                "unknown", f"no trial is offered for {model} and {purpose!r} as {occasion}"
            )
        placed = await self._identities.identity(tenant, by)
        if placed is None:
            raise TrialError("unknown", f"the identity {by!r} is not known to {tenant!r}")
        document = {"purpose": purpose, "occasion": occasion, "model": model, "reason": reason}
        digest = await self._objects.put(_canonical(document))
        async with self._work.transaction(tenant):
            await self._ledger.record(
                tenant,
                Fact(
                    kind=DECLINED,
                    refs=LedgerRefs(tenant=tenant, actor=placed.identity),
                    outcome=occasion,
                    content_digest=digest,
                ),
            )

    async def offers(self, tenant: Tenant) -> list[Offer]:
        """The trials offered now, less those a person declined since their occasion arose."""
        found = await self._offered(tenant)
        async with self._work.transaction(tenant):
            entries = await self._ledger.of_kinds(tenant, {DECLINED})
        declined: list[tuple[datetime, str, str, str]] = []
        for entry in entries:
            content = (
                None
                if entry.content_digest is None
                else await self._objects.get(entry.content_digest)
            )
            if content is None:
                continue
            said = json.loads(content)
            declined.append((entry.ts, said["purpose"], said["occasion"], said["model"]))
        return [
            o
            for o in found
            if not any(
                (purpose, occasion, model) == (o.purpose, o.occasion, o.model)
                and (o.since is None or at >= o.since)
                for at, purpose, occasion, model in declined
            )
        ]

    async def _offered(self, tenant: Tenant) -> list[Offer]:
        """The trials offered now, for every purpose a step of the tenant's active processes
        asks for. An offer stands until a trial of its purpose includes its model, started
        after the occasion."""
        purposes: set[str] = set()
        async with self._work.transaction(tenant):
            processes = await self._processes.list(tenant)
            for process in processes:
                if process.active_version is None:
                    continue
                version = await self._versions.get(tenant, f"{process.id}@{process.active_version}")
                if version is not None:
                    purposes |= _purposes(version)
            entries = await self._ledger.of_kinds(tenant, {STEP_FINISHED, OFFERED})
        trials = await self.of_tenant(tenant)
        members = [adapter for adapter, _, _ in self._models.members()]
        answered: dict[str, list[tuple[datetime, str | None]]] = {}
        for entry in entries:
            if entry.kind == STEP_FINISHED and entry.adapter is not None:
                answered.setdefault(entry.adapter, []).append((entry.ts, _model_of(entry)))
        offers: list[Offer] = []
        for purpose in sorted(purposes):
            chain = await self._models.chain(purpose)
            if not chain:
                continue
            first = chain[0].adapter
            candidates = (first, *(m for m in members if m != first))
            seen = answered.get(first, [])
            if not seen and not _tried(trials, purpose, first, None):
                offers.append(
                    Offer(
                        purpose=purpose,
                        occasion="introduced",
                        model=first,
                        candidates=candidates,
                        reason=f"{first} serves {purpose} and has answered no step yet",
                    )
                )
            changed = _changed(seen)
            if changed is not None and not _tried(trials, purpose, first, changed[0]):
                at, before, now = changed
                offers.append(
                    Offer(
                        purpose=purpose,
                        occasion="changed",
                        model=first,
                        candidates=candidates,
                        reason=f"{first} answered as {before} and answers as {now} since then",
                        since=at,
                    )
                )
        for entry in entries:
            if entry.kind != OFFERED or entry.content_digest is None:
                continue
            content = await self._objects.get(entry.content_digest)
            if content is None:
                continue
            proposed = json.loads(content)
            purpose, candidate = proposed["purpose"], proposed["candidate"]
            if _tried(trials, purpose, candidate, entry.ts):
                continue
            chain = await self._models.chain(purpose)
            current = [m.adapter for m in chain[:1]]
            offers.append(
                Offer(
                    purpose=purpose,
                    occasion="proposed",
                    model=candidate,
                    candidates=tuple(dict.fromkeys((candidate, *current))),
                    reason=str(proposed.get("reason") or ""),
                    since=entry.ts,
                )
            )
        return offers


def _purposes(version: ProcessVersion) -> set[str]:
    """The purposes the version's steps on a language model ask for."""
    examples = {name: given.example for name, given in version.inputs.items()}
    found: set[str] = set()
    for step in version.ordered():
        try:
            work = parse_work(step, version.work.get(step.id), examples)
        except RunError:
            continue
        if isinstance(work, LlmWork):
            found.add(work.purpose)
    return found


def _tried(trials: Sequence[Trial], purpose: str, model: str, since: datetime | None) -> bool:
    """Whether a trial of the purpose included the model, started at or after `since`."""
    return any(
        t.purpose == purpose and model in t.candidates and (since is None or t.started_at >= since)
        for t in trials
    )


def _model_of(entry: LedgerEntry) -> str | None:
    """The model the provider reported for the step: the entry's own, or the one its tokens
    were recorded under."""
    if entry.model:
        return entry.model
    tokens = None if entry.consumption is None else entry.consumption.tokens_by_model
    return None if not tokens else sorted(tokens)[0]


def _changed(seen: Sequence[tuple[datetime, str | None]]) -> tuple[datetime, str, str] | None:
    """When the model a member answered as last changed, from what to what; None where it
    never changed. Read in the ledger's order; a step that reported no model is passed over."""
    latest: tuple[datetime, str, str] | None = None
    previous: str | None = None
    for at, model in seen:
        if model is None:
            continue
        if previous is not None and model != previous:
            latest = (at, previous, model)
        previous = model
    return latest


def _canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()


__all__ = ["Trials"]
