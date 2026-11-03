"""Use case: recurring decisions become rules on proposal (ADR-0161, UC-7.10, issue #648).

Four acts, each recorded in the ledger:

- **Propose.** Every decision that took effect is looked at with the others of its kind — the
  same anchor, at the same step of the same process. Where the most recent of them show a
  consistent pattern (`domain/service/precedent.py`), Taktus raises a decision request that
  proposes a rule answering that kind with the option the precedents chose, and names every
  precedent. The rule is stored `proposed` and answers nothing: `rule.proposed`.
- **Adopt or decline.** The proposal is decided as any request is: answered, its reading sent
  back and confirmed. Option A taken without modifications adopts the rule, with the person who
  decided as its actor (`rule.adopted`); any other answer declines it (`rule.declined`), and the
  kind is proposed again only after as many new decisions agree once more.
- **Answer.** A request raised later of an adopted rule's kind takes effect at once with the
  rule's option: applied, with its register entry naming the rule, and no person as its actor
  (`rule.applied`). The request is still raised and still in the register; only nobody waits.
- **Retire.** A person retires an adopted rule (`rule.retired`). From then on the kind is asked
  again.

Which processes and steps a request belongs to is read from the ledger: the run's
`run.created` names its version. No rule is ever proposed for, or answers, a request a rule may
not answer (`precedent.refusal`): the act stays with a person.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import timedelta

from taktus.components.decision.application.service.errors import DecisionError, NotRaised
from taktus.components.decision.application.service.raise_request import (
    RaiseRequest,
    RaiseRequestHandler,
)
from taktus.components.decision.domain.model import (
    DecisionRule,
    Kind,
    RegisterEntry,
    Request,
    RuleStatus,
    entry_id,
)
from taktus.components.decision.domain.model.recorded import APPLIED
from taktus.components.decision.domain.service import precedent
from taktus.ports.clock import Clock
from taktus.ports.ledger import Fact, Ledger
from taktus.ports.persistence import Repository, Tenant, UnitOfWork
from taktus.shared.v1 import (
    AnswerInterpreted,
    DecisionClass,
    DecisionStatus,
    LedgerRefs,
)

PROPOSED = "rule.proposed"
ADOPTED = "rule.adopted"
DECLINED = "rule.declined"
ANSWERED = "rule.applied"
RETIRED = "rule.retired"
ADOPT = "A"
"""The option of a proposal that adopts the rule."""


class UnknownRule(DecisionError):
    """No such rule, or none that can be retired."""


class PrecedentRules:
    def __init__(
        self,
        rules: Repository[DecisionRule],
        register: Repository[RegisterEntry],
        requests: Repository[Request],
        work: UnitOfWork,
        ledger: Ledger,
        clock: Clock,
        decision_days: int = 3,
    ) -> None:
        self._rules = rules
        self._register = register
        self._requests = requests
        self._work = work
        self._ledger = ledger
        self._clock = clock
        self._decision_days = decision_days
        # The proposal is raised as any request is, and is never answered by a rule itself.
        self._raising = RaiseRequestHandler(requests, work, ledger, clock)

    # --- the read side ---------------------------------------------------------------------

    async def all(self, tenant: Tenant) -> list[DecisionRule]:
        """Every rule of the tenant, in the order it was proposed."""
        async with self._work.transaction(tenant):
            found = await self._rules.list(tenant)
        return sorted(found, key=lambda r: (r.created_at, r.id))

    # --- answer: inside the transaction that raises a request -------------------------------

    async def answering(self, tenant: Tenant, request: Request) -> DecisionRule | None:
        """The adopted rule that answers the request, or None. Called inside the transaction
        that stores it."""
        shaped = request.request
        if request.anchor is None or precedent.refusal(shaped.class_, request.anchor) is not None:
            return None
        process = await self._process_of(tenant, shaped.raised_by.run)
        if process is None:
            return None
        kind = Kind(process=process, step_id=shaped.raised_by.step, anchor=request.anchor)
        for rule in await self._rules.list(tenant):
            if rule.status is RuleStatus.ADOPTED and rule.kind == kind:
                if rule.decider == request.decider:
                    return rule
        return None

    async def answer(self, tenant: Tenant, request: Request, rule: DecisionRule) -> Request:
        """The request applied with the rule's option, its register entry naming the rule.
        Called inside the transaction that stored the request."""
        now = self._clock.now()
        shaped = request.request
        option = next((o for o in shaped.options if o.id == rule.option), None)
        if option is None:
            return request  # the request offers no such option: a person answers it
        answered = f"answered by the rule {rule.id}, adopted by {rule.decided_by}"
        entry = RegisterEntry.model_validate(
            {
                "id": entry_id(request.id),
                "tenant": request.tenant,
                "request_id": request.id,
                "run_id": shaped.raised_by.run,
                "step_id": shaped.raised_by.step,
                "class": shaped.class_,
                "anchor": request.anchor,
                "decider": request.decider,
                "option": option.id,
                "proposal": option.proposal,
                "modifications": None,
                "answer_raw": answered,
                "decided_by": rule.actor,
                "raised_at": request.raised_at,
                "answered_at": now,
                "decided_at": now,
                "rule": rule.id,
            }
        )
        applied = request.model_copy(
            update={
                "request": shaped.model_copy(
                    update={
                        "status": DecisionStatus.APPLIED,
                        "answer_raw": answered,
                        "answer_interpreted": AnswerInterpreted(option=option.id),
                        "outcome": entry.id,
                    }
                ),
                "answered_at": now,
                "decided_by": rule.actor,
                "decided_at": now,
            }
        )
        await self._register.put(tenant, entry)
        await self._requests.put(tenant, applied)
        refs = LedgerRefs(
            tenant=tenant,
            run_id=shaped.raised_by.run,
            step_id=shaped.raised_by.step,
            decision_request_id=request.id,
        )
        outcome = f"option_{option.id.lower()}"
        await self._ledger.record(
            tenant,
            Fact(kind=APPLIED, refs=refs, outcome=outcome, content_digest=_digest(entry)),
        )
        await self._ledger.record(
            tenant, Fact(kind=ANSWERED, refs=refs, outcome=outcome, content_digest=_digest(rule))
        )
        return applied

    # --- propose, adopt, decline: after a decision took effect ------------------------------

    async def decided(self, tenant: Tenant, entry: RegisterEntry) -> DecisionRule | None:
        """A decision took effect. One that answers a proposal adopts or declines its rule; any
        other is looked at with its kind, and a pattern is proposed. Returns the rule that
        changed or was proposed, or None."""
        async with self._work.transaction(tenant):
            rules = await self._rules.list(tenant)
        proposed = next((r for r in rules if r.request_id == entry.request_id), None)
        if proposed is not None:
            return await self._settle(tenant, proposed, entry)
        if entry.rule is not None or precedent.refusal(entry.class_, entry.anchor) is not None:
            return None
        return await self._propose(tenant, entry, rules)

    async def _settle(
        self, tenant: Tenant, rule: DecisionRule, entry: RegisterEntry
    ) -> DecisionRule | None:
        if rule.status is not RuleStatus.PROPOSED:
            return None
        adopted = entry.option == ADOPT and entry.modifications is None
        settled = rule.model_copy(
            update={
                "status": RuleStatus.ADOPTED if adopted else RuleStatus.DECLINED,
                "decided_by": entry.decided_by,
                "decided_at": entry.decided_at,
            }
        )
        async with self._work.transaction(tenant):
            await self._rules.put(tenant, settled)
            await self._record(tenant, settled, ADOPTED if adopted else DECLINED, entry.decided_by)
        return settled

    async def _propose(
        self, tenant: Tenant, entry: RegisterEntry, rules: Sequence[DecisionRule]
    ) -> DecisionRule | None:
        async with self._work.transaction(tenant):
            process = await self._process_of(tenant, entry.run_id)
            if process is None or entry.anchor is None:
                return None
            kind = Kind(process=process, step_id=entry.step_id, anchor=entry.anchor)
            mine = [r for r in rules if r.kind == kind]
            if any(r.status in (RuleStatus.PROPOSED, RuleStatus.ADOPTED) for r in mine):
                return None  # one proposal at a time, and none beside a rule in force
            since = max((r.decided_at for r in mine if r.decided_at is not None), default=None)
            of_kind = []
            for candidate in await self._register.list(tenant):
                if candidate.step_id != kind.step_id or candidate.anchor != kind.anchor:
                    continue
                if await self._process_of(tenant, candidate.run_id) == process:
                    of_kind.append(candidate)
        of_kind.sort(key=lambda e: (e.decided_at, e.id))
        found = precedent.pattern(kind, of_kind, since=since)
        if found is None:
            return None
        rule_id = "dru_" + _hash(f"{tenant}\n{process}\n{kind.step_id}\n{kind.anchor}\n{since}")
        request_id = "dr_" + _hash(f"rule\n{rule_id}")
        last = found.precedents[-1]
        names = ", ".join(p.id for p in found.precedents)
        try:
            await self._raising.execute(
                RaiseRequest(
                    tenant=tenant,
                    id=request_id,
                    run=last.run_id,
                    step=last.step_id,
                    class_=str(DecisionClass.STRATEGIC),
                    situation=(
                        f"The anchor {kind.anchor} at step {kind.step_id} of the process "
                        f"{process} was decided {len(found.precedents)} times in a row with "
                        f"option {found.option} — {found.proposal} — and without modifications: "
                        f"{names}."
                    ),
                    question=(
                        f"Shall every later request of the anchor {kind.anchor} at step "
                        f"{kind.step_id} of {process} be answered with option {found.option} "
                        "by rule, without asking?"
                    ),
                    options=[
                        {
                            "id": "A",
                            "proposal": f"Adopt the rule: answer it with option {found.option}.",
                            "consequence": "The act is no longer asked of the role; each answer "
                            "stays in the register, naming the rule, and the rule can be "
                            "retired at any time.",
                            "recommended": True,
                            "reason": f"{len(found.precedents)} decisions in a row chose "
                            f"option {found.option} without changing it.",
                        },
                        {
                            "id": "B",
                            "proposal": "Keep asking the role every time.",
                            "consequence": "Nothing changes; the rule is proposed again only "
                            f"after {precedent.PRECEDENTS} more decisions agree.",
                            "recommended": False,
                        },
                    ],
                    blocking=[],
                    due=self._clock.now().date() + timedelta(days=self._decision_days),
                    decider=found.decider,
                )
            )
        except NotRaised:
            return None
        rule = DecisionRule(
            id=rule_id,
            tenant=tenant,
            kind=kind,
            option=found.option,
            proposal=found.proposal,
            decider=found.decider,
            precedents=tuple(p.id for p in found.precedents),
            request_id=request_id,
            created_at=self._clock.now(),
        )
        async with self._work.transaction(tenant):
            await self._rules.put(tenant, rule)
            await self._record(tenant, rule, PROPOSED, None)
        return rule

    # --- retire ----------------------------------------------------------------------------

    async def retire(self, tenant: Tenant, rule_id: str, by: str) -> DecisionRule:
        """An adopted rule retired by a person: it answers nothing from now on."""
        async with self._work.transaction(tenant):
            rule = await self._rules.get(tenant, rule_id)
            if rule is None or rule.status is not RuleStatus.ADOPTED:
                raise UnknownRule(f"no adopted rule {rule_id!r} of tenant {tenant!r}")
            retired = rule.model_copy(
                update={
                    "status": RuleStatus.RETIRED,
                    "decided_by": by,
                    "decided_at": self._clock.now(),
                }
            )
            await self._rules.put(tenant, retired)
            await self._record(tenant, retired, RETIRED, by)
        return retired

    # --- helpers ---------------------------------------------------------------------------

    async def _process_of(self, tenant: Tenant, run_id: str) -> str | None:
        """The process a run belongs to, from its `run.created`; None when the ledger does not
        name one. Inside a transaction."""
        for entry in await self._ledger.entries(tenant, run_id):
            version = entry.refs.process_version
            if entry.kind == "run.created" and version is not None:
                return version.split("@", 1)[0]
        return None

    async def _record(
        self, tenant: Tenant, rule: DecisionRule, kind: str, actor: str | None
    ) -> None:
        await self._ledger.record(
            tenant,
            Fact(
                kind=kind,
                refs=LedgerRefs(
                    tenant=tenant,
                    step_id=rule.kind.step_id,
                    decision_request_id=rule.request_id,
                    actor=actor,
                ),
                outcome=str(rule.status),
                content_digest=_digest(rule),
            ),
        )


def _hash(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _digest(value: DecisionRule | RegisterEntry) -> str:
    canonical = json.dumps(value.document(), ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
