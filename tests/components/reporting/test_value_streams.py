"""The organisation seen as value streams (UC-15.6, ADR-0159 §5 and §6): a map in three tiers
with each stream's autonomy and method mix, flow efficiency, blocked share and the department
boundaries it crosses, and one stream as role swimlanes with the structure overlaid. Pure: no
figure names a person, a role's waiting is withheld below two holders, nothing is stored."""

from __future__ import annotations

from taktus.components.reporting.domain.service import streams as v

ORDER = v.ProcessFacts(
    process="order",
    name="Order",
    version="order@2",
    level=3,
    steps=(
        v.StepFacts(id="read", method="llm", exactness="tolerant", fallback_role="sales"),
        v.StepFacts(id="price", method="rule", exactness="exact"),
        v.StepFacts(id="accept", method="human", role="sales"),
    ),
    runs=(
        v.RunFacts(lead_seconds=3600, blocked={"wait.human": 1800}),
        v.RunFacts(lead_seconds=3600, blocked={"limit.provider": 600}),
    ),
    waits={"sales": 1800},
)
INVOICE = v.ProcessFacts(
    process="invoice",
    name="Invoice",
    version="invoice@1",
    level=2,
    steps=(
        v.StepFacts(id="book", method="rule", exactness="exact"),
        v.StepFacts(id="release", method="human", role="accounting"),
    ),
    waits={"accounting": 7200},
)
HIRING = v.ProcessFacts(process="hiring", name="Hiring", version="hiring@1", level=1)
LOOSE = v.ProcessFacts(process="loose", name="Loose")

ROLES = {
    "sales": v.RoleFacts(holders=3, units=("acme/sales",)),
    "accounting": v.RoleFacts(holders=1, units=("acme/finance",)),
}

CASH = v.StreamFacts(
    stream="order-to-cash",
    revision=2,
    name="Order to cash",
    kind="core",
    trigger="A customer wants to buy",
    outcome="the customer has what they paid for",
    role="sales-lead",
    processes=("order", "invoice"),
)
PEOPLE = v.StreamFacts(
    stream="people",
    revision=1,
    name="People",
    kind="support",
    trigger="A position is open",
    outcome="it is filled",
    role="hr",
    processes=("hiring",),
)


def test_the_map_holds_three_tiers_and_the_processes_no_stream_names() -> None:
    drawn = v.stream_map([PEOPLE, CASH], [ORDER, INVOICE, HIRING, LOOSE], ROLES, 30)
    assert [c.stream for c in drawn.core] == ["order-to-cash"]
    assert [c.stream for c in drawn.support] == ["people"] and drawn.management == ()
    assert [o.process for o in drawn.outside] == ["loose"]
    assert drawn.summary == (
        "1 core, 0 management and 1 support streams over 30 days; 1 process in no stream."
    )


def test_a_stream_shows_its_mix_its_flow_its_blocked_share_and_its_crossings() -> None:
    (card,) = v.stream_map([CASH], [ORDER, INVOICE], ROLES, 30).core
    figures = card.figures
    assert figures.steps == 5
    assert figures.autonomy == {"2": 0.4, "3": 0.6}
    assert figures.methods == {"human": 0.4, "llm": 0.2, "rule": 0.4}
    assert figures.reproducible == 0.4
    assert figures.runs == 2
    assert figures.flow_efficiency == round((7200 - 2400) / 7200, 4)
    assert figures.blocked_share == round(2400 / 7200, 4)
    assert figures.top_cause == "wait.human"
    (crossing,) = figures.crossings
    assert (crossing.from_step, crossing.to_step) == ("accept", "release")
    assert (crossing.from_units, crossing.to_units) == (("acme/sales",), ("acme/finance",))
    assert "1 department boundary crossed" in card.text
    assert card.role == "sales-lead"


def test_a_handover_within_a_unit_or_to_a_role_nobody_places_crosses_nothing() -> None:
    same = {"sales": ROLES["sales"], "accounting": v.RoleFacts(holders=2, units=("acme/sales",))}
    (card,) = v.stream_map([CASH], [ORDER, INVOICE], same, 30).core
    assert card.figures.crossings == ()
    (unplaced,) = v.stream_map([CASH], [ORDER, INVOICE], {}, 30).core
    assert unplaced.figures.crossings == ()


def test_a_stream_without_a_finished_run_says_so_and_shows_no_flow() -> None:
    (card,) = v.stream_map([PEOPLE], [HIRING], {}, 7).support
    assert card.figures.flow_efficiency is None and card.figures.blocked_share is None
    assert "no run ended in the period" in card.text


def test_a_stream_opens_as_role_swimlanes_with_the_structure_overlaid() -> None:
    lanes = v.stream_lanes(CASH, [ORDER, INVOICE], ROLES)
    assert [c.process for c in lanes.columns] == ["order", "invoice"]
    assert [lane.key for lane in lanes.lanes] == [
        "taktus.reproducible",
        "taktus.variable",
        "role:sales",
        "role:accounting",
    ]
    chips = {(c.process, c.step): c for c in lanes.chips}
    assert chips[("order", "read")].lane == "taktus.variable"
    assert chips[("order", "read")].fallback_lane == "role:sales"
    assert chips[("order", "price")].lane == "taktus.reproducible"
    assert chips[("invoice", "release")].lane == "role:accounting"
    sales, accounting = lanes.lanes[2:]
    assert sales.units == ("acme/sales",) and sales.waiting_seconds == 1800
    assert accounting.waiting_seconds is None, "one holder: the figure would be a person's"
    assert "too few hold it" in accounting.text
    assert lanes.units == ("acme/finance", "acme/sales")


def test_no_view_carries_a_field_that_could_hold_a_person() -> None:
    drawn = v.stream_map([CASH], [ORDER, INVOICE], ROLES, 30).document()
    lanes = v.stream_lanes(CASH, [ORDER, INVOICE], ROLES).document()

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {k for x in value.values() for k in keys(x)}
        if isinstance(value, list):
            return {k for x in value for k in keys(x)}
        return set()

    found = keys(drawn) | keys(lanes)
    assert not found & {"identity", "person", "actor", "holder", "identities", "by", "name_of"}
