"""The acts of building, done for a person through the services every surface uses (ADR-0324,
ADR-0325, UC-1.11, UC-1.14).

The closed list of acts is the command component's (`ACTS`). Here each act is done: a plan
draft opened, answered, set and commissioned through the plan dialogue (ADR-0237); a change or
a description of a process asked through the request path (ADR-0091 §2, ADR-0251); a proposal
rehearsed, commissioned and discarded, and a process rolled back (ADR-0091 §3 to §5); a process
started by the one start command (ADR-0131 §5). Each acts as the person, through the same
checks as the web app — registration's rights among them (ADR-0257).

- **Read back by rule.** What an act will do is said from the act and its arguments, looked
  up where a name is needed; never by a language model.
- **Kept until the yes.** `propose` keeps an act read back in the person's conversation;
  `confirm` does it on their yes, or records their no, and says what came of it.
- **What the person may see.** An act on a process asks the visibility predicate first; a
  process the person may not see is answered as one that does not exist.

This is wiring: an act crosses the command, process and run components.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from taktus.adapters.driving.rest.wiring import BuildRefused, PlanActs, ProposalActs, StartRefused
from taktus.components.command.application.service import PlanningError
from taktus.components.command.application.service.conversations import (
    ConversationError,
    Conversations,
)
from taktus.components.command.domain.model.conversation import (
    ACTS,
    ActRefused,
    ActState,
    ProposedAct,
    validated,
)
from taktus.components.command.domain.service.guided import Mode
from taktus.components.process.application.service.proposals import ProposalError, Proposals
from taktus.components.process.domain.model import InvalidProcess, Proposal
from taktus.components.reporting.domain.model import ProcessRef, Reader
from taktus.components.reporting.domain.service import visibility
from taktus.components.run.domain.model import DemandToAccept
from taktus.composition.agent_surface import AgentSurface
from taktus.ports.identity import Resolution

type Json = dict[str, Any]

AGENT = "channel.agent"
"""The channel an act a person's own agent does at once arrives on (ADR-0131 §5)."""
SHOWN = 160
"""The longest a value is quoted in a read-back, in characters."""


def _quote(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= SHOWN else text[: SHOWN - 1] + "…"


def _raise(given: Json) -> str:
    return (
        " You approve the raise of an autonomy level it makes."
        if given.get("approve_raise")
        else ""
    )


class BuildActs:
    def __init__(
        self,
        *,
        planning: PlanActs,
        proposals: Proposals,
        acts: ProposalActs | None,
        agent: AgentSurface,
        conversations: Conversations,
    ) -> None:
        self._planning = planning
        self._proposals = proposals
        self._acts = acts
        self._agent = agent
        self._conversations = conversations

    # --- reads --------------------------------------------------------------------------------

    async def plans(self, who: Resolution) -> list[Json]:
        drafts = await self._planning.mine(who.tenant, who.identity)
        return [self._planning.view(d, Mode.EXPERT) for d in drafts]

    async def plan(self, who: Resolution, draft: str, mode: Mode = Mode.GUIDED) -> Json:
        try:
            found = await self._planning.get(who.tenant, who.identity, draft)
        except PlanningError as error:
            raise BuildRefused(str(error)) from error
        return self._planning.view(found, mode)

    async def proposals(self, who: Resolution, process: str) -> list[Json]:
        self._seen(who, process)
        return [p.document() for p in await self._proposals.of_process(who.tenant, process)]

    async def proposal(self, who: Resolution, process: str, proposal: str) -> Json:
        return (await self._proposal(who, process, proposal)).document()

    # --- read-back and confirmation -----------------------------------------------------------

    async def read_back(self, who: Resolution, act: str, arguments: Mapping[str, Any]) -> str:
        """What the act will do, said by rule; `BuildRefused` for an act off the list, with
        arguments that do not fit it, or on something the person may not see."""
        try:
            given = validated(act, arguments)
        except ActRefused as error:
            raise BuildRefused(str(error)) from error
        process = given.get("process")
        if isinstance(process, str) and act != "ask_description":
            self._seen(who, process)
        if act == "open_plan":
            return f"Open a plan draft for “{_quote(given['said'])}”. Nothing runs yet."
        if act == "answer_plan":
            return (
                f"Answer {given['field']} of plan draft {given['draft']} with "
                f"{_quote(given['value'])}."
            )
        if act == "set_plan":
            return f"Set {', '.join(sorted(given['fields']))} of plan draft {given['draft']}."
        if act == "commission_plan":
            view = await self.plan(who, given["draft"], Mode.EXPERT)
            goal = view["draft"].get("goal") or "no goal yet"
            return (
                f"Commission plan draft {given['draft']} (“{_quote(goal)}”): what it plans starts."
            )
        if act == "ask_change":
            return (
                f"Have a run propose a change of {process}: “{_quote(given['request'])}”. "
                "Nothing is registered."
            )
        if act == "ask_description":
            return (
                f"Have a run propose a new process {process}: “{_quote(given['description'])}”. "
                "Nothing is registered."
            )
        if act == "rehearse_proposal":
            return f"Rehearse proposal {given['proposal']} of {process}; nothing leaves the system."
        if act == "commission_proposal":
            found = await self._proposal(who, str(process), given["proposal"])
            return (
                f"Commission proposal {found.id}: version {found.version} becomes the active "
                f"version of {process}." + _raise(given)
            )
        if act == "discard_proposal":
            return f"Discard proposal {given['proposal']} of {process}."
        if act == "rollback_process":
            return (
                f"Make version {given['version']} of {process} current again, as a new version."
                + _raise(given)
            )
        inputs = given.get("inputs") or {}
        return f"Start {process}" + (f" with {_quote(inputs)}." if inputs else ".")

    async def propose(
        self, who: Resolution, act: str, arguments: Mapping[str, Any], channel: str
    ) -> ProposedAct:
        """The act read back and kept waiting for the person's yes."""
        said = await self.read_back(who, act, arguments)
        return await self._conversations.propose(
            who.tenant, who.identity, channel, act, arguments, said
        )

    async def waiting(self, who: Resolution, act_id: str) -> ProposedAct:
        try:
            return await self._conversations.waiting(who.tenant, who.identity, act_id)
        except ConversationError as error:
            raise BuildRefused(str(error)) from error

    async def confirm(
        self, who: Resolution, act_id: str, yes: bool, *, say: bool = True
    ) -> ProposedAct:
        """The person's yes does the act; their no records that nothing was done. Either is
        said as Taktus's next turn where `say`."""
        waiting = await self.waiting(who, act_id)
        if not yes:
            return await self._conversations.settle(
                who.tenant, who.identity, act_id, ActState.DECLINED, "Not done.", say=say
            )
        try:
            outcome, links = await self.do(
                who, waiting.act, waiting.arguments, channel=waiting.channel
            )
        except BuildRefused as refused:
            return await self._conversations.settle(
                who.tenant,
                who.identity,
                act_id,
                ActState.FAILED,
                f"Not done: {refused}",
                say=say,
            )
        return await self._conversations.settle(
            who.tenant, who.identity, act_id, ActState.DONE, outcome, links, say=say
        )

    # --- the acts -----------------------------------------------------------------------------

    async def do(
        self, who: Resolution, act: str, arguments: Mapping[str, Any], *, channel: str = AGENT
    ) -> tuple[str, dict[str, str]]:
        """The act done as the person, on the channel it was asked on: what came of it, in one
        line, and what it created."""
        try:
            given = validated(act, arguments)
        except ActRefused as error:
            raise BuildRefused(str(error)) from error
        process = given.get("process")
        if isinstance(process, str) and act != "ask_description":
            self._seen(who, process)
        try:
            return await self._do(who, act, given, channel)
        except DemandToAccept as error:
            raise BuildRefused(
                f"{error}; seen the demand, ask again with accept_demand true"
            ) from error
        except (PlanningError, ProposalError, StartRefused, ValueError, ValidationError) as error:
            raise BuildRefused(str(error)) from error
        except InvalidProcess as error:
            raise BuildRefused("registration refused it: " + "; ".join(error.findings)) from error

    async def _do(
        self, who: Resolution, act: str, given: Json, channel: str
    ) -> tuple[str, dict[str, str]]:
        tenant, identity = who.tenant, who.identity
        planning = self._planning
        if act == "open_plan":
            draft = await planning.open(tenant, identity, who.org_path, given["said"])
            return self._drafted(draft.id, planning.view(draft, Mode.GUIDED), "is open")
        if act == "answer_plan":
            draft = await planning.answer(
                tenant,
                identity,
                given["draft"],
                given["field"],
                given["value"],
                step_id=given.get("step_id"),
            )
            return self._drafted(draft.id, planning.view(draft, Mode.GUIDED), "is answered")
        if act == "set_plan":
            draft = await planning.set(tenant, identity, given["draft"], given["fields"])
            return self._drafted(draft.id, planning.view(draft, Mode.GUIDED), "is set")
        if act == "commission_plan":
            plan, run = await planning.commission_and_start(
                tenant, identity, given["draft"], accept_demand=bool(given.get("accept_demand"))
            )
            links = {"draft": given["draft"], "plan": plan.id}
            if run is not None:
                links["run"] = run.id
                return f"Plan {plan.id} is commissioned; run {run.id} started.", links
            return f"Plan {plan.id} is commissioned.", links
        if act == "start_process":
            run = await self._agent.start(
                who, given["process"], given.get("inputs") or {}, channel=channel
            )
            return f"Run {run.id} of {given['process']} started.", {"run": run.id}
        acts = self._acts
        if acts is None:
            raise BuildRefused("this instance takes no change of a process in dialogue")
        process = str(given["process"])
        approve_raise = bool(given.get("approve_raise"))
        # The person's own approval of a raise, given with the act and read back with it.
        if act in ("ask_change", "ask_description"):
            exists = await self._exists(who, process)
            if act == "ask_change" and not exists:
                raise BuildRefused(f"no process {process!r} that you may see")
            if act == "ask_description" and exists:
                raise BuildRefused(f"{process} exists already: ask for a change of it instead")
            words = given["request"] if act == "ask_change" else given["description"]
            run = await acts.ask(tenant, process, words, identity)
            return (
                f"Run {run.id} works out the proposal; it appears under {process}'s proposals.",
                {"run": run.id, "process": process},
            )
        if act == "rehearse_proposal":
            proposal, run = await acts.rehearse(
                tenant, process, given["proposal"], identity, given.get("inputs")
            )
            return (
                f"Proposal {proposal.id} is rehearsing in run {run.id}; nothing leaves the system.",
                {"run": run.id, "proposal": proposal.id, "process": process},
            )
        if act == "commission_proposal":
            version = await acts.commission(
                tenant,
                process,
                given["proposal"],
                identity,
                approved_by=identity if approve_raise else None,
                override=given.get("override"),
            )
            return (
                f"Version {version.version} of {process} is active.",
                {"process": process, "version": version.version},
            )
        if act == "discard_proposal":
            discarded = await self._proposals.discard(tenant, process, given["proposal"])
            return f"Proposal {discarded.id} is discarded.", {"process": process}
        if act == "rollback_process":
            version = await acts.rollback(
                tenant,
                process,
                given["version"],
                identity,
                as_version=given.get("as_version"),
                approved_by=identity if approve_raise else None,
            )
            return (
                f"{process} is at version {given['version']} again, as version {version.version}.",
                {"process": process, "version": version.version},
            )
        raise BuildRefused(f"{act!r} is not an act Taktus can do")  # unreachable: validated

    # --- helpers ------------------------------------------------------------------------------

    @staticmethod
    def _drafted(draft: str, view: Json, did: str) -> tuple[str, dict[str, str]]:
        question = view.get("question")
        asks = f" Next: {question['asks']}" if question else ""
        missing = view.get("missing") or []
        lacks = f" Missing: {', '.join(missing)}." if missing and not question else ""
        return f"Plan draft {draft} {did}.{asks}{lacks}", {"draft": draft}

    @staticmethod
    def _seen(who: Resolution, process: str) -> None:
        reader = Reader(
            tenant=who.tenant, identity=who.identity, roles=who.roles, unseen=who.unseen
        )
        if not visibility.may_see_process(reader, ProcessRef(id=process, tenant=who.tenant)):
            raise BuildRefused(f"no process {process!r} that you may see")

    async def _exists(self, who: Resolution, process: str) -> bool:
        listed = await self._agent.processes(who)
        return any(p["process"] == process for p in listed)

    async def _proposal(self, who: Resolution, process: str, proposal: str) -> Proposal:
        self._seen(who, process)
        try:
            return await self._proposals.get(who.tenant, process, proposal)
        except ProposalError as error:
            raise BuildRefused(str(error)) from error


__all__ = ["ACTS", "BuildActs", "BuildRefused"]
