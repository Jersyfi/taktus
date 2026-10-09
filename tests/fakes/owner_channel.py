"""The owner-facing channel over memory, wired as the composition root wires it, with a carrier
that records what it was told to deliver instead of a connector (ADR-0045).

`OwnerChannel` holds the identity, decision and reporting components over one memory store, the
owner `idn_owner` holding the role `owner`, a colleague the owner named, and an outsider. The
channel is configured from the shipped German phrasebook, as this tenant's owner reads German.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fakes.clock import FakeClock
from fakes.identity import Directory, directory
from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.reporting.application.service import (
    Answer,
    AnswerInChannel,
    ConfigureChannel,
    RaiseReport,
)
from taktus.components.reporting.domain.model import OwnerChannel as Channel
from taktus.components.reporting.domain.model import Report, ReportKind
from taktus.components.reporting.ports import Deliveries, NotDelivered, Sent
from taktus.components.run.ports import Draft, DraftOption
from taktus.composition.decisions import DecisionWiring, decision_wiring
from taktus.composition.owner_channel import KnownSecrets, OwnerChannelWiring, owner_channel_wiring

TENANT = "t"
OWNER = "idn_owner"
NAMED = "idn_deputy"
OUTSIDER = "idn_outsider"
CHANNEL = "channel.chat"
ADDRESS = "D0000000001"
SECRET = "sk-0123456789abcdef-a-value-nobody-may-read"  # noqa: S105 — a test value


@dataclass
class Said:
    channel: str
    address: str
    text: str
    thread: str | None
    key: str


@dataclass
class Task:
    capability: str
    operation: str
    title: str
    body: str
    key: str


@dataclass
class RecordingDeliveries(Deliveries):
    """Delivers into a list. A top-level message opens a thread of its own; a repeat of a key
    is found and said once, as a marked connector would."""

    said: list[Said] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    fails: str | None = None
    """When set, every delivery fails with this reason."""

    async def say(
        self,
        tenant: str,
        channel: str,
        address: str,
        text: str,
        *,
        thread: str | None = None,
        key: str,
    ) -> Sent | NotDelivered:
        if self.fails is not None:
            return NotDelivered(reason=self.fails)
        for n, s in enumerate(self.said, start=1):
            if s.key == key:
                return Sent(thread=s.thread or f"170000000{n}.000100", record=f"chat.message:{n}")
        self.said.append(Said(channel, address, text, thread, key))
        n = len(self.said)
        return Sent(
            thread=thread or f"170000000{n}.000100",
            record=f"chat.message:{address}/{n}",
        )

    async def open_task(
        self,
        tenant: str,
        capability: str,
        operation: str,
        title: str,
        body: str,
        *,
        key: str,
    ) -> Sent | NotDelivered:
        if self.fails is not None:
            return NotDelivered(reason=self.fails)
        self.tasks.append(Task(capability, operation, title, body, key))
        n = len(self.tasks)
        return Sent(record=f"issue:{n}", url=f"https://tickets.example/issues/{n}")

    def in_thread(self, thread: str) -> list[str]:
        return [s.text for s in self.said if s.thread == thread]


@dataclass
class OwnerChannel:
    identity: Directory
    decisions: DecisionWiring
    owner: OwnerChannelWiring
    deliveries: RecordingDeliveries
    clock: FakeClock

    @property
    def persistence(self) -> Any:
        return self.identity.persistence

    async def configure(self, **overrides: Any) -> Channel:
        document: dict[str, Any] = {
            "owner": OWNER,
            "named": [NAMED],
            "channel": CHANNEL,
            "address": ADDRESS,
            "language": "de",
        }
        document.update(overrides)
        return await self.owner.configure.execute(
            ConfigureChannel(tenant=TENANT, document=document, actor="operator")
        )

    def due(self, days: int = 7) -> date:
        return self.clock.current.date() + timedelta(days=days)

    async def need(self, id: str = "need_0001", **overrides: Any) -> Report:
        given: dict[str, Any] = {
            "tenant": TENANT,
            "id": id,
            "kind": ReportKind.NEED,
            "title": "Taktus's app in the chat workspace",
            "needed": ["The app's bot token and signing secret, in two files."],
            "steps": ["Create the app from the manifest.", "Write each value into its file."],
            "standing_still": ["The live test of the chat connector."],
            "due": self.due(),
            "links": [("Issue", "https://repository.example/issues/146")],
        }
        given.update(overrides)
        return await self.owner.raising.execute(RaiseReport(**given))

    async def date(self, id: str = "date_0001") -> Report:
        return await self.owner.raising.execute(
            RaiseReport(
                tenant=TENANT,
                id=id,
                kind=ReportKind.DATE,
                title="Storage runs out",
                needed=["More storage for the state volume."],
                steps=["Grow the volume, or delete what the retention allows."],
                standing_still=["Every run, once the volume is full."],
                due=self.due(10),
            )
        )

    async def failure(self, id: str = "fail_0001") -> Report:
        return await self.owner.failure(
            TENANT,
            id,
            "The repository service stopped behaving as its adapter expects",
            needed=["A look at what the service changed."],
            steps=["Read the failed calls in the run's ledger.", "Adapt or pin the adapter."],
            standing_still=["P-03 Implementation, at its first step on the repository."],
            due=self.due(1),
            links=[("Run", "https://taktus.example/runs/run_7")],
        )

    async def decision(self, id: str = "dr_0001", decider: str = "owner") -> Report | None:
        """A decision request raised as the run raises one — through the run's decision port —
        which reports it to the owner when its role is one the channel carries."""
        await self.decisions.requests.raise_request(
            TENANT,
            Draft(
                id=id,
                run="run_1",
                step="release",
                class_="legal",
                situation="Run run_1 has reached step release, whose act is anchored.",
                question="Does Taktus release the payment?",
                options=(
                    DraftOption(
                        id="A",
                        proposal="Release it.",
                        consequence="The payment leaves the account today.",
                        recommended=True,
                        reason="The registered process proposes it here.",
                    ),
                    DraftOption(
                        id="B",
                        proposal="Do not release it.",
                        consequence="The run halts at the step.",
                        recommended=False,
                    ),
                ),
                blocking=("run_1", "run_1/release"),
                due=self.due(3),
                decider=decider,
                anchor="anc-legal",
            ),
        )
        return await self.owner.queries.one(TENANT, id)

    def thread_of(self, report: Report) -> str:
        message = report.message()
        assert message is not None and message.thread is not None, report.deliveries
        return message.thread

    async def answer(
        self, report: Report, text: str, identity: str | None = OWNER, event: str = "Ev1"
    ) -> Answer:
        answered = await self.owner.answering.execute(
            AnswerInChannel(
                tenant=TENANT,
                channel=CHANNEL,
                address=ADDRESS,
                thread=self.thread_of(report),
                identity=identity,
                text=text,
                event=event,
            )
        )
        assert answered is not None, "the message is in the report's thread"
        return answered

    async def kinds(self) -> list[str]:
        return await self.identity.kinds(TENANT)


def owner_channel(
    *, secrets: tuple[str, ...] = (SECRET,), environment: Mapping[str, str] | None = None
) -> OwnerChannel:
    clock = FakeClock()
    identity = directory((TENANT,), clock=clock)
    persistence = identity.persistence

    def of(kind: Any) -> Any:
        return MemoryRepository(persistence, kind)

    decisions = decision_wiring(of, persistence, identity.ledger, clock, identity.directory)
    deliveries = RecordingDeliveries()
    owner = owner_channel_wiring(
        of,
        persistence,
        identity.ledger,
        clock,
        connectors=_NoConnectors(),
        answer=decisions.answer,
        confirm=decisions.confirm,
        secrets=KnownSecrets(secrets),
        deliveries=deliveries,
    )
    decisions.requests.report_to(owner.decision_raised)
    return OwnerChannel(identity, decisions, owner, deliveries, clock)


class _NoConnectors:
    async def resolve(self, capability: str) -> None:
        return None


async def people(given: OwnerChannel) -> None:
    """The owner holds the role `owner`; the named colleague holds it too; the outsider is a
    person of the tenant who holds it and was not named."""
    for name in (OWNER, NAMED, OUTSIDER):
        await given.identity.directory.add(TENANT, name, (TENANT,), roles=("owner",))
