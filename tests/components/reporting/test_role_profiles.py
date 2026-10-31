"""A role's profile, derived from the processes it takes part in (UC-15.7, ADR-0167 §3 to §5).

Pure: the facts in, the profile out. What the processes need of the role, never a person's file;
figures that persons' work produced are withheld below two holders, Taktus's are not.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from taktus.components.reporting.domain.service import profiles
from taktus.components.reporting.domain.service.profiles import (
    AnchorFacts,
    CheckFacts,
    Facts,
    OpenWaitFacts,
    ProcessFacts,
    Ran,
    RequestFacts,
    StepFacts,
    StreamFacts,
    WaitFacts,
)


def facts(holders: int = 2, **more: Any) -> Facts:
    steps = (
        StepFacts(
            id="classify",
            method="ml",
            reason="six fixed classes",
            fallback_human=True,
            fallback_when="confidence < 0.9",
            fallback_role="accounting",
            fallback_expertise=("chart of accounts",),
        ),
        StepFacts(
            id="book",
            method="human",
            reason="a person books it",
            role="accounting",
            expertise=("double entry", "chart of accounts"),
            task="book the invoice",
        ),
        StepFacts(
            id="total",
            method="rule",
            reason="a sum",
            checks=(CheckFacts(kind="approval", role="controlling"), CheckFacts(kind="bounds")),
        ),
        StepFacts(id="release", method="rule", reason="release the payment", ask_role="accounting"),
        StepFacts(id="sign", method="human", reason="the owner signs"),
    )
    given: dict[str, Any] = {
        "processes": (ProcessFacts(process="invoice", version="invoice@3", steps=steps),),
        "streams": (
            StreamFacts(stream="procure", name="Procure to pay", role="accounting"),
            StreamFacts(stream="order", name="Order to cash", role="sales", processes=("invoice",)),
            StreamFacts(stream="hire", name="Hire to retire", role="people", processes=("hr",)),
        ),
        "anchors": (
            AnchorFacts(
                id="payment", class_="legal", act="release a payment", decider="accounting"
            ),
            AnchorFacts(id="contract", class_="legal", act="sign a contract", decider="owner"),
        ),
        "requests": (
            RequestFacts(decider="accounting", due=date(2026, 11, 3)),
            RequestFacts(decider="accounting", due=date(2026, 11, 1)),
            RequestFacts(decider="owner", due=date(2026, 11, 2)),
        ),
        "waits": (
            WaitFacts(process="invoice", step="book", role="accounting", seconds=600),
            WaitFacts(process="invoice", step="classify", role="accounting", seconds=300),
            WaitFacts(process="invoice", step="sign", role=None, seconds=50),
        ),
        "open_waits": (OpenWaitFacts(process="invoice", step="book", role="accounting"),),
        "ran": (
            Ran(process="invoice", step="classify", automatic=40, manual=0),
            Ran(process="invoice", step="book", automatic=0, manual=12),
        ),
        "holders": {"accounting": holders, "owner": 1},
        "units": {"accounting": ("acme/finance",)},
        "days": 30,
    }
    return Facts.model_validate({**given, **more})


def test_the_profile_lists_what_the_processes_need_of_the_role() -> None:
    p = profiles.profile(facts(), "accounting")
    assert [s.stream for s in p.responsible_for] == ["procure"]
    assert [s.stream for s in p.serves] == ["order"], "a stream of a process it acts in"
    (book,) = p.performs
    assert (book.step, book.task, book.expertise) == (
        "book",
        "book the invoice",
        ("double entry", "chart of accounts"),
    )
    (classify,) = p.takes_over
    assert (classify.step, classify.when) == ("classify", "confidence < 0.9")
    assert [(d.kind, d.ref) for d in p.decides] == [
        ("anchor", "payment"),
        ("ask", "invoice/release"),
    ]
    assert p.supervises == ()
    assert p.expertise == ("double entry", "chart of accounts"), "each once"
    assert p.units == ("acme/finance",)
    assert p.load.open_waits == 1
    assert p.load.performed.value == 12
    assert (p.load.if_taktus_stopped_steps, p.load.if_taktus_stopped_runs) == (1, 40)
    assert p.waiting.seconds.value == 900
    assert (p.requests.open, p.requests.oldest_due) == (2, date(2026, 11, 1))
    controlling = profiles.profile(facts(), "controlling")
    assert [(s.step, s.check) for s in controlling.supervises] == [("total", "approval")]
    assert [s.stream for s in controlling.serves] == ["order"], "it checks a step of it"
    assert profiles.profile(facts(), "people").serves == (), "it acts in no process here"


def test_a_step_naming_no_role_counts_for_the_owner() -> None:
    owner = profiles.profile(facts(), "owner")
    assert [d.step for d in owner.performs] == ["sign"]
    assert [d.ref for d in owner.decides] == ["contract"]
    assert "owner" in profiles.roles(facts())


def test_figures_of_persons_work_are_withheld_below_two_holders_and_taktuss_are_not() -> None:
    p = profiles.profile(facts(holders=1, own={"accounting": 600.0}), "accounting")
    assert p.load.performed.value is None and "withheld" in (p.load.performed.withheld or "")
    assert p.waiting.seconds.value is None and p.waiting.seconds.withheld is not None
    assert p.waiting.own_seconds == 600.0, "the holder sees their own beside it"
    assert p.load.if_taktus_stopped_runs == 40, "what Taktus performs is the process's"
    assert p.load.open_waits == 1
    assert "900" not in p.text and "12 time" not in p.text


def _fields(model: type[BaseModel]) -> set[str]:
    found: set[str] = set()
    for name, field in model.model_fields.items():
        found.add(name)
        annotation = field.annotation
        for inner in getattr(annotation, "__args__", (annotation,)):
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                found |= _fields(inner)
    return found


def test_no_field_holds_a_person_or_says_whether_one_is_needed() -> None:
    named = _fields(profiles.RoleProfile) | _fields(profiles.RoleIndex)
    forbidden = ("person", "identity", "holder", "headcount", "fte", "staff", "needed")
    assert not {f for f in named if any(word in f for word in forbidden)}, named
    p = profiles.profile(facts(), "accounting")
    assert "strategic anchor" in p.workforce and "DEC-0029" in p.review
    assert p.review in p.text


def test_the_export_is_a_draft_without_time_figures_or_the_readers_own() -> None:
    p = profiles.profile(facts(own={"accounting": 777.0}), "accounting")
    text = profiles.description(p)
    assert text.startswith("# Draft position description: role `accounting`")
    assert "DEC-0029" in text and "§87(1) no. 6 BetrVG" in text
    assert "strategic anchor" in text
    assert "book the invoice" in text and "chart of accounts" in text
    assert "release a payment" in text and "Procure to pay" in text
    assert "1 step(s) Taktus performs now would come to the role." in text
    for figure in ("900", "777", "600", "seconds", "12"):
        assert figure not in text, figure


def test_the_index_holds_every_role_the_structure_or_the_processes_name() -> None:
    index = profiles.index(facts())
    assert [r.role for r in index.roles] == [
        "accounting",
        "controlling",
        "owner",
        "people",
        "sales",
    ]
    accounting = next(r for r in index.roles if r.role == "accounting")
    assert (accounting.performs, accounting.takes_over, accounting.open_requests) == (1, 1, 2)
    assert index.review == profiles.REVIEW
