"""What governs the work, on the HTTP surface (ADR-0122, issue #563).

`GET /autonomy`: each process the reader may see, with its stated level and why, the level a
rule lowered it to, and its correction rates per process and action class over 7 and 28 days.
No figure names the person who decided (principle 14, ADR-0015).

`GET /findings` and its review: the instance's own findings with their classification, for the
owner and whom the owner named; an answer in review read back before it acts, and only what was
read back done (ADR-0008, ADR-0118 §4).
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta

import httpx

from taktus.adapters.driven.memory import MemoryObjectStore
from taktus.components.reporting.application.service import Kept, ProductFindings, Sending
from taktus.components.reporting.domain.model import Blocked, Shipped, ShippedAdapter
from taktus.components.reporting.ports import Held
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

from .conftest import OTHER, TENANT, Services
from .test_owner_reports import NAMED, OWNER, configured
from .test_process_level import bearer, bundle, register
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

DECIDER = "idn_ada_who_corrected"
"""The person who answered every proposal: named in the answer's own entry, never in a figure."""


async def decided(
    given: Services, outcome: str, *, action: str | None = None, tenant: str = TENANT
) -> None:
    """One decision on a proposal, as the run records it: the answer's entry names the person,
    `proposal.decided` names none (ADR-0110 §2)."""
    refs = {
        "tenant": tenant,
        "process_version": "invoices@1",
        "run_id": "run_1",
        "step_id": "draft",
    }
    async with given.persistence.transaction(tenant):
        await given.ledger.record(
            tenant,
            Fact(kind="step.confirmed", refs=LedgerRefs(**refs, actor=DECIDER), outcome="ok"),
        )
        await given.ledger.record(
            tenant,
            Fact(kind="proposal.decided", refs=LedgerRefs(**refs, action=action), outcome=outcome),
        )


async def test_the_levels_need_an_account_key(client: Client) -> None:
    http, _, base = client
    is_problem(await http.get(f"{base}/autonomy"), 401)
    is_problem(await http.get(f"{base}/autonomy", headers=bearer("nothing")), 401)


async def test_each_process_shows_its_level_why_and_its_rates_per_process_and_action(
    client: Client,
) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    for outcome in ("released", "released", "corrected", "rejected"):
        await decided(given, outcome)
    await decided(given, "released", action="mail.send")
    given.clock.current += timedelta(days=10)
    await decided(given, "corrected", action="mail.send")
    _, key = await given.identities.add(TENANT, "idn_reader", (TENANT,))

    answer = await http.get(f"{base}/autonomy", headers=bearer(key))
    assert answer.status_code == 200, answer.text
    [process] = answer.json()["processes"]
    assert (process["id"], process["version"], process["in_force"]) == ("invoices", "1", 2)
    assert process["stated"]["reason"] == "a person confirms"
    assert process["text"] == "Runs at autonomy level 2: a person confirms."
    units = {u["action"]: u for u in process["units"]}
    assert set(units) == {None, "mail.send"}, "counted per process and per action class"
    own = units[None]
    assert (own["week"]["decided"], own["week"]["rate"]) == (0, None), "ten days ago"
    assert (own["month"]["decided"], own["month"]["rate"]) == (4, 0.5)
    assert own["month"]["corrected"] == 1 and own["month"]["rejected"] == 1
    mail = units["mail.send"]
    assert mail["level"] == 2, "the process's level, where the statement sets none for it"
    assert (mail["week"]["decided"], mail["week"]["rate"]) == (1, 1.0)
    assert mail["text"].startswith("The action mail.send: 1 of 1 corrected or rejected")
    assert answer.json()["limits"]["lower_rate"] == 0.25
    assert answer.json()["limits"]["shipped_default"] is True


async def test_no_figure_names_the_person_who_corrected(client: Client) -> None:
    """Principle 14, ADR-0015: the answer holds counts per process and action class only."""
    http, given, base = client
    await register(given, bundle("1"))
    for outcome in ("corrected", "rejected", "released"):
        await decided(given, outcome)
        await decided(given, outcome, action="mail.send")
    _, key = await given.identities.add(TENANT, "idn_reader", (TENANT,))
    answer = await http.get(f"{base}/autonomy", headers=bearer(key))
    assert DECIDER not in answer.text, "no figure names the person who decided"

    def keys(node: object) -> set[str]:
        if isinstance(node, dict):
            return set(node) | {k for v in node.values() for k in keys(v)}
        if isinstance(node, list):
            return {k for v in node for k in keys(v)}
        return set()

    assert not keys(answer.json()) & {"actor", "by", "person", "identity", "who", "decider"}


async def test_a_level_lowered_by_rule_is_in_force_with_why(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    for _ in range(4):
        await decided(given, "rejected")
    verdict_after = await given.corrections.lowered(TENANT, "invoices@1")
    assert verdict_after.level is None, "the surface counts; it lowers nothing itself"
    async with given.persistence.transaction(TENANT):
        await given.ledger.record(
            TENANT,
            Fact(
                kind="autonomy.lowered",
                refs=LedgerRefs(tenant=TENANT, process_version="invoices@1", run_id="run_1"),
                outcome="level_1",
            ),
        )
    _, key = await given.identities.add(TENANT, "idn_reader", (TENANT,))
    [process] = (await http.get(f"{base}/autonomy", headers=bearer(key))).json()["processes"]
    assert (process["stated"]["level"], process["lowered"]["level"], process["in_force"]) == (
        2,
        1,
        1,
    )
    assert process["text"].startswith("Runs at autonomy level 1, lowered by rule from the stated 2")


async def test_a_process_of_another_tenant_is_never_shown(client: Client) -> None:
    http, given, base = client
    await register(given, bundle("1"), tenant=OTHER)
    await decided(given, "corrected", tenant=OTHER)
    _, key = await given.identities.add(TENANT, "idn_reader", (TENANT,))
    seen = (await http.get(f"{base}/autonomy", headers=bearer(key))).json()
    assert seen["processes"] == [] and seen["summary"] == "No process you may see."


# --- findings ----------------------------------------------------------------------------------


@dataclass
class Channel:
    """The repository in memory, as `tests/components/reporting/test_product_findings.py`."""

    issues: dict[str, Held] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return "findings.memory"

    async def held(self, tenant: str) -> Sequence[Held]:
        return list(self.issues.values())

    async def open(self, tenant: str, title: str, body: str, *, key: str) -> str:
        reference = str(len(self.issues) + 1)
        self.issues[reference] = Held(reference=reference, open=True, texts=(body,))
        return reference

    async def add(self, tenant: str, reference: str, text: str, *, key: str) -> None:
        held = self.issues[reference]
        self.issues[reference] = held.model_copy(update={"texts": (*held.texts, text)})


@dataclass
class Source:
    found: list[Blocked] = field(default_factory=list)

    async def blocks(self, tenant: str) -> Sequence[Blocked]:
        return list(self.found)


class _Content:
    async def values(self, tenant: str) -> Sequence[str]:
        return []


class _Randomness:
    def token(self, length: int) -> str:
        return secrets.token_hex(length)


SHIPPED = Shipped(
    workers=(ShippedAdapter(name="coder", capabilities=("code.edit",)),),
    connectors=(ShippedAdapter(name="repo", capabilities=("repository.issues",)),),
)


def findings_of(given: Services, level: str, channel: Channel) -> ProductFindings:
    at = given.clock.now()
    source = Source(
        [
            Blocked(
                cause="no_worker", run_id="run_1", step_id="build", since=at, lacking="code.review"
            ),
            Blocked(
                cause="no_worker", run_id="run_2", step_id="edit", since=at, lacking="code.edit"
            ),
        ]
    )
    kept = Kept(given.ledger, MemoryObjectStore(), given.persistence, _Randomness(), _Content())
    sending = (
        None if level == "off" else Sending(channel, "http://findings.invalid/mcp", level=level)  # type: ignore[arg-type]
    )
    return ProductFindings(source, kept, sending, shipped=SHIPPED)


async def test_findings_are_read_by_the_owner_and_whom_the_owner_named_only(
    client: Client,
) -> None:
    http, given, base = client
    keys = await configured(given)
    is_problem(await http.get(f"{base}/findings"), 401)
    is_problem(await http.get(f"{base}/findings", headers=keys["idn_outsider"]), 403)
    is_problem(await http.get(f"{base}/findings", headers=keys[OWNER]), 404)
    given.findings = findings_of(given, "review", Channel())
    for who in (OWNER, NAMED):
        assert (await http.get(f"{base}/findings", headers=keys[who])).status_code == 200
    body = {"answer": "local"}
    is_problem(
        await http.post(f"{base}/findings/x/review", json=body, headers=keys["idn_outsider"]), 403
    )


async def test_each_finding_carries_its_classification_and_the_words_it_would_leave_in(
    client: Client,
) -> None:
    http, given, base = client
    keys = await configured(given)
    given.findings = findings_of(given, "review", Channel())
    seen = (await http.get(f"{base}/findings", headers=keys[OWNER])).json()
    assert seen["level"] == "review" and seen["in_review"] == 1
    by = {f["lack"]["lacking"]: f for f in seen["findings"]}
    assert by["code.review"]["kind"] == "product" and by["code.review"]["in_review"] is True
    assert by["code.edit"]["kind"] == "configuration" and by["code.edit"]["leaves"] is False
    assert by["code.edit"]["classified"]["adapters"] == ["coder"]
    assert by["code.review"]["text"].startswith("Product finding: no worker offers code.review")
    assert seen["summary"] == "2 lacks met, 1 of them kept here; 1 waits for a review."


async def test_an_answer_in_review_is_read_back_and_only_its_confirmation_acts(
    client: Client,
) -> None:
    http, given, base = client
    keys = await configured(given)
    channel = Channel()
    given.findings = findings_of(given, "review", channel)
    [candidate] = [
        f
        for f in (await http.get(f"{base}/findings", headers=keys[OWNER])).json()["findings"]
        if f["in_review"]
    ]
    lack = candidate["lack"]["key"]

    read = await http.post(
        f"{base}/findings/{lack}/review", json={"answer": "send"}, headers=keys[OWNER]
    )
    assert read.status_code == 200, read.text
    reading = read.json()
    assert reading["reading"].startswith("You answer send")
    assert reading["text"] == candidate["text"], "exactly what would leave"
    assert channel.issues == {}, "reading back does nothing"

    rejected = await http.post(
        f"{base}/findings/{lack}/review/confirm",
        json={"answer": "send", "confirmation": reading["confirmation"], "confirmed": False},
        headers=keys[OWNER],
    )
    assert rejected.json()["done"] is False and channel.issues == {}

    other = await http.post(
        f"{base}/findings/{lack}/review/confirm",
        json={"answer": "local", "confirmation": reading["confirmation"], "confirmed": True},
        headers=keys[OWNER],
    )
    is_problem(other, 409)
    by_another = await http.post(
        f"{base}/findings/{lack}/review/confirm",
        json={"answer": "send", "confirmation": reading["confirmation"], "confirmed": True},
        headers=keys[NAMED],
    )
    is_problem(by_another, 409)
    assert channel.issues == {}, "a confirmation of something not read back does nothing"

    done = await http.post(
        f"{base}/findings/{lack}/review/confirm",
        json={"answer": "send", "confirmation": reading["confirmation"], "confirmed": True},
        headers=keys[OWNER],
    )
    assert done.status_code == 200, done.text
    assert done.json()["message"] == "Sent: 1 opened, 0 added."
    assert len(channel.issues) == 1


async def test_local_for_us_is_remembered_and_never_offered_again(client: Client) -> None:
    http, given, base = client
    keys = await configured(given)
    channel = Channel()
    given.findings = findings_of(given, "review", channel)
    seen = (await http.get(f"{base}/findings", headers=keys[OWNER])).json()
    [lack] = [f["lack"]["key"] for f in seen["findings"] if f["in_review"]]
    reading = (
        await http.post(
            f"{base}/findings/{lack}/review", json={"answer": "local"}, headers=keys[OWNER]
        )
    ).json()
    done = await http.post(
        f"{base}/findings/{lack}/review/confirm",
        json={"answer": "local", "confirmation": reading["confirmation"], "confirmed": True},
        headers=keys[OWNER],
    )
    assert done.json()["done"] is True
    again = (await http.get(f"{base}/findings", headers=keys[OWNER])).json()
    assert again["in_review"] == 0 and channel.issues == {}
    [called] = [f for f in again["findings"] if f["lack"]["key"] == lack]
    assert called["kind"] == "local_for_us" and called["leaves"] is False
    is_problem(
        await http.post(
            f"{base}/findings/{lack}/review", json={"answer": "send"}, headers=keys[OWNER]
        ),
        409,
    )


async def test_at_the_level_off_nothing_is_in_review(client: Client) -> None:
    http, given, base = client
    keys = await configured(given)
    given.findings = findings_of(given, "off", Channel())
    seen = (await http.get(f"{base}/findings", headers=keys[OWNER])).json()
    assert seen["level"] == "off" and seen["in_review"] == 0
    assert "the operator's level is off" in seen["summary"]
    lack = seen["findings"][0]["lack"]["key"]
    refused = await http.post(
        f"{base}/findings/{lack}/review", json={"answer": "send"}, headers=keys[OWNER]
    )
    assert "level is off" in json.dumps(is_problem(refused, 409))
