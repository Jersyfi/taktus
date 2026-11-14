"""The form of every message Taktus writes to a person (ADR-0316 §2-§5, DEC-0239), as a gate.

Every report a raiser writes, and a role's scheduled report, is rendered from a realistic record
in the two shipped phrasebooks. Each message must lead with one headline, stay short, speak the
phrasebook's language in every line of Taktus's own, and keep identifiers in its addresses.

- **Short.** At most `BUDGET` characters without its addresses; a message with several quoted
  items or list lines may add `PER_LINE` characters for each one after the first.
- **One language.** A line that is not a quote of the record carries no word of the other
  language once the values it names are set aside.
- **No identifier as text.** No run identifier, no process reference (`name@version`), outside an
  address or a quote.
- **No empty heading.** No line ends in a colon with nothing after it.

The fixtures are the records the raisers write: the escalation of 2026-11-14 with its long error,
a summary of a backlog, a decision request, a need, a stage, a page edited by hand, a sender of
findings, a broken interface, every kind of alert, a recurring failure, a chain halted, a
contract deviation, a red signal, the daily report of signals and a role's report.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from taktus.components.governance.domain.model.escalation import ByHand, Escalated
from taktus.components.reporting.domain.model import (
    Brief,
    Link,
    Offered,
    OwnerChannel,
    Phrasebook,
    Report,
    ReportKind,
    Said,
)
from taktus.components.reporting.domain.service import rendering
from taktus.components.reporting.domain.service.reports import Composed, Item
from taktus.composition.escalations import brief_of

ROOT = Path(__file__).resolve().parents[3]
BOOKS = ROOT / "src/taktus/composition/phrasebooks"
BUDGET = 400
PER_LINE = 120
BASE = "https://taktus.example/instance"
AT = datetime(2026, 11, 14, 9, 30, tzinfo=UTC)
DUE = date(2026, 11, 14)

ENGLISH_ONLY = frozenset(
    "the and of is which stopped failed needed step run with not this what resume leave "
    "older open outside within waits".split()
)
GERMAN_ONLY = frozenset(
    "der die das und ist nicht bei steht wurde schritt auf mit eine ältere offen weitere "
    "außerhalb wartet".split()
)
OTHER = {"de": ENGLISH_ONLY, "en": GERMAN_ONLY}

LONG_ERROR = (
    "the agent ended without a result: claude exited with status 1 after 41 turns; the last "
    "tool call was a test run that failed in tests/composition/test_escalations.py with an "
    "AssertionError about the number of messages delivered, and the worker's checkpoint holds "
    "the diff of 14 files and 612 lines" * 2
)


def channel(language: str, *, view: bool = True) -> OwnerChannel:
    book = json.loads((BOOKS / f"{language}.json").read_text(encoding="utf-8"))
    return OwnerChannel(
        id="t",
        tenant="t",
        owner="owner@example.org",
        channel="channel.chat",
        address="D0000000001",
        phrasebook=Phrasebook.model_validate(book),
        view_base=f"{BASE}/" if view else None,
        configured_at=AT,
        configured_by="operator",
    )


def report(kind: ReportKind, *, brief: Brief | None = None, **given: Any) -> Report:
    fields: dict[str, Any] = {
        "id": "report-1",
        "tenant": "t",
        "kind": kind,
        "title": "A record's title, written by Taktus in English",
        "needed": ("A record's needed item.",),
        "steps": ("A record's step.",),
        "standing_still": ("A record's work standing still.",),
        "due": DUE,
        "offered": (Offered(id="done", label="done"),),
        "raised_at": AT,
        "brief": brief,
    }
    fields.update(given)
    return Report(**fields)


def escalation() -> tuple[Report, tuple[str, ...]]:
    """The message of 2026-11-14: a step that failed with a long error, after six steps."""
    record = Escalated(
        run_id="run_e57a0c41d2",
        process_version="p03-implementation@6",
        escalated_at=AT,
        step_id="implement",
        cause="failure",
        reason=LONG_ERROR,
        attempts=1,
        finished=("read-issue", "plan", "branch", "context", "estimate", "claim"),
        reached=("worker.coding", "connector.repository"),
        left=1,
        by_hand=ByHand(
            system="the repository",
            do="Implement the issue on a branch and open a pull request.",
            expertise="Python",
            credentials=("repository_token",),
            done="a pull request is open",
        ),
    )
    name = "Issue to pull request"
    return report(
        ReportKind.FAILURE,
        id="escalation-run_e57a0c41d2-1",
        links=(Link(label="run run_e57a0c41d2", url=f"{BASE}/app/#/runs/run_e57a0c41d2"),),
        brief=brief_of(record, name),
    ), (name, "implement")


def fixtures() -> list[tuple[str, Report, tuple[str, ...]]]:
    """Every report a raiser writes, by name, with the values its brief names."""
    found: list[tuple[str, Report, tuple[str, ...]]] = []
    escalated, values = escalation()
    found.append(("escalation", escalated, values))
    found.append(
        (
            "backlog",
            report(
                ReportKind.FAILURE,
                id="escalations-owner-20261114T0930",
                needed=tuple(f"Process {n} at step s: run run_{n}." for n in range(80)),
                brief=Brief(
                    headline=Said(entry="backlog", values={"count": "80"}),
                    ask=Said(entry="backlog_ask"),
                ),
            ),
            ("80",),
        )
    )
    found.append(
        (
            "decision",
            report(
                ReportKind.DECISION,
                id="dr_0001",
                title="Run run_1 has reached step release, whose act is anchored.",
                needed=("Does Taktus release the payment of 1,240.00 EUR to the supplier?",),
                offered=(
                    Offered(
                        id="A", label="Release it. The payment leaves today.", recommended=True
                    ),
                    Offered(id="B", label="Hold it until the invoice is checked by hand."),
                ),
            ),
            (),
        )
    )
    found.append(
        (
            "need",
            report(
                ReportKind.NEED,
                id="need_0001",
                title="Taktus's app in the chat workspace",
                needed=("The app's bot token and signing secret, in two files.",),
                links=(Link(label="Issue", url="https://repository.example/issues/146"),),
            ),
            (),
        )
    )
    for entry, values in (
        ("stage_proposed", {"stage": "Bookkeeping"}),
        ("stage_fell", {"stage": "Bookkeeping"}),
        ("page_edited", {"page": "guides/operator/backup"}),
        ("sender", {}),
    ):
        found.append(
            (
                entry,
                report(
                    ReportKind.NEED,
                    needed=(
                        "A person's approval to open the stage 'bookkeeping': the stage before "
                        "it holds",
                        "Figures of 'bookkeeping': open 2.0 week(s); 41 run(s) finished; 0 missed",
                    ),
                    brief=Brief(headline=Said(entry=entry, values=values)),
                ),
                tuple(values.values()),
            )
        )
    for entry, values, ask, quote in (
        (
            "interface_broken",
            {"interface": "connector.repository"},
            "interface_ask",
            "authentication",
        ),
        (
            "recurred",
            {"process": "Invoice intake", "step": "extract", "count": "5"},
            "recurred_ask",
            None,
        ),
        (
            "chain_halted",
            {"chain": "Order to cash", "step": "invoice"},
            "escalated_ask",
            "the input 'order' is missing",
        ),
        (
            "deviated",
            {"process": "Supplier invoices", "step": "read"},
            "deviated_ask",
            "the clause `frequency` expects one every 1d; it arrived 3h after the one before",
        ),
        *(
            (f"alert_{kind}", {}, None, "The backup of 2026-11-13 is missing.")
            for kind in ("capacity", "claim_lost", "backup", "lowered", "raise", "local_lack")
        ),
    ):
        found.append(
            (
                entry,
                report(
                    ReportKind.FAILURE,
                    brief=Brief(
                        headline=Said(entry=entry, values=values),
                        quote=quote,
                        ask=None if ask is None else Said(entry=ask),
                    ),
                ),
                tuple(values.values()),
            )
        )
    case = "https://tickets.example/board/cost"
    run = f"{BASE}/app/#/runs/run_m"
    found.append(
        (
            "signal_red",
            report(
                ReportKind.FAILURE,
                links=(Link(label="Case", url=case), Link(label="Run", url=run)),
                brief=Brief(
                    headline=Said(entry="signal_red", values={"signal": "cost.cloud_daily"}),
                    items=(
                        Said(
                            entry="red",
                            values={
                                "signal": "cost.cloud_daily",
                                "value": "412",
                                "threshold": "150",
                            },
                            links=(case, run),
                        ),
                    ),
                    ask=Said(entry="signal_ask"),
                ),
            ),
            ("cost.cloud_daily", "412", "150"),
        )
    )
    lines = tuple(
        Said(
            entry=level,
            values={"signal": f"signal.{n}", "value": "120", "threshold": "100"}
            if level != "unmeasured"
            else {"signal": f"signal.{n}"},
            links=(case, run),
        )
        for n, level in enumerate(["red", "yellow", "yellow", "unmeasured"] * 3)
    )
    found.append(
        (
            "signals",
            report(
                ReportKind.SIGNALS,
                offered=(
                    Offered(id="done", label="done"),
                    Offered(id="start-throttle", label="start throttle-cloud"),
                ),
                brief=Brief(
                    headline=Said(
                        entry="signals_deviating",
                        values={"date": "2026-11-14", "deviating": "9", "unmeasured": "3"},
                    ),
                    items=lines,
                ),
            ),
            (
                "2026-11-14",
                "9",
                "3",
                "120",
                "100",
                "throttle-cloud",
                *(f"signal.{n}" for n in range(12)),
            ),
        )
    )
    return found


def bare(message: str, values: tuple[str, ...]) -> list[str]:
    """The lines of Taktus's own: no quote of the record, no address, no identifier in
    parentheses, and none of the values the brief names."""
    lines = []
    for line in message.splitlines():
        if line.startswith("> "):
            continue
        line = re.sub(r"https?://\S+", "", line)
        line = re.sub(r"\([a-z0-9_.-]+\)", "", line)
        for value in sorted(values, key=len, reverse=True):
            line = line.replace(value, "")
        lines.append(line)
    return lines


def length(message: str) -> int:
    return len(re.sub(r"https?://\S+", "", message))


def listed(message: str) -> int:
    return sum(1 for line in message.splitlines() if line.startswith(("> ", "• ")))


CASES = [(language, name) for language in ("de", "en") for name, _, _ in fixtures()]


@pytest.mark.parametrize(("language", "name"), CASES)
def test_every_message_is_short_in_one_language_and_names_no_identifier(
    language: str, name: str
) -> None:
    [(_, found, values)] = [f for f in fixtures() if f[0] == name]
    for configured in (channel(language), channel(language, view=False)):
        said = rendering.message(found, configured)
        assert said.startswith("*"), "one headline first"
        allowed = BUDGET + PER_LINE * max(0, listed(said) - 1)
        assert length(said) <= allowed, f"{length(said)} > {allowed}:\n{said}"
        for line in bare(said, values):
            words = set(re.findall(r"[a-zäöüß]+", line.casefold()))
            assert not words & OTHER[language], f"{sorted(words & OTHER[language])} in {line!r}"
            assert not re.search(r"\brun_[0-9a-z]+|@\d+\b", line), line
        for line in said.splitlines():
            assert not line.rstrip().endswith(":"), f"an empty heading: {line!r}"
            assert len(re.sub(r"https?://\S+", "", line)) <= PER_LINE + 20, line


def test_the_escalation_of_2026_11_14_is_short_and_keeps_its_package_out_of_the_message() -> None:
    found, _ = escalation()
    said = rendering.message(found, channel("de"))
    lines = said.splitlines()
    assert lines[0] == "*Störung: Issue to pull request steht bei Schritt implement*"
    assert lines[1].startswith("> failure: the agent ended") and lines[1].endswith("…")
    assert len(lines[1]) <= rendering.QUOTE + 2, "the error on one line, cut"
    assert "(this package lacks" not in said and "not in the record" not in said
    assert f"{BASE}/app/#/reports/escalation-run_e57a0c41d2-1" in said, "one link to it all"
    assert length(said) <= 400


def test_a_list_carries_only_so_many_lines_and_counts_the_rest() -> None:
    [(_, signals, _)] = [f for f in fixtures() if f[0] == "signals"]
    said = rendering.message(signals, channel("de"))
    items = [line for line in said.splitlines() if line.startswith("• ")]
    assert len(items) == rendering.LISTED + 1
    assert items[-1] == "• 4 weitere auf der Seite"


def test_a_role_s_report_is_said_in_the_tenant_s_language_one_line_each_with_its_link() -> None:
    composed = Composed(
        title="Report daily for owner",
        items=(
            Item(kind="decision", ref="dr_0007", text="Decision request dr_0007 waits."),
            Item(
                kind="escalation",
                ref="run_9",
                text="Run run_9 of invoices escalated.",
                values={"process": "invoices"},
            ),
            Item(
                kind="blocked",
                ref="run_8",
                text="Run run_8 of invoices waits at approve for owner.",
                values={"process": "invoices", "step": "approve"},
            ),
            Item(kind="figure", ref="lead-time", text="lead-time missed its target."),
        ),
        lines=("Report daily for owner",),
        quiet=False,
    )
    said = rendering.role_message(composed, "owner", channel("de"))
    assert said is not None
    lines = said.splitlines()
    assert lines[0] == "*Bericht für owner: 4 zum Ansehen*"
    assert lines[1] == f"• Eine Entscheidung wartet auf dich {BASE}/app/#/reports/dr_0007"
    assert lines[2] == f"• invoices eskaliert {BASE}/app/#/runs/run_9"
    assert lines[3] == f"• invoices wartet bei Schritt approve {BASE}/app/#/runs/run_8"
    assert lines[4] == "> lead-time missed its target.", (
        "a figure with its value, as the view has it"
    )
    assert "GET /" not in said
    quiet = composed.model_copy(update={"items": (), "quiet": True})
    assert rendering.role_message(quiet, "owner", channel("de")) == (
        "Bericht für owner: nichts außerhalb des Rahmens"
    )


def test_a_phrasebook_without_short_forms_still_sends_a_short_message() -> None:
    """A tenant's own phrasebook configured before `briefs` existed: the title, as a quote."""
    configured = channel("de")
    old = configured.model_copy(
        update={"phrasebook": configured.phrasebook.model_copy(update={"briefs": None})}
    )
    found, _ = escalation()
    said = rendering.message(found.model_copy(update={"title": LONG_ERROR}), old)
    assert said.splitlines()[0] == "*Störung*"
    assert said.splitlines()[1].startswith("> ") and length(said) <= 400


def test_a_short_form_s_sentence_names_exactly_its_values() -> None:
    book = json.loads((BOOKS / "de.json").read_text(encoding="utf-8"))
    book["briefs"]["escalated"] = "{process} steht"
    with pytest.raises(ValueError, match=r"briefs\.escalated"):
        Phrasebook.model_validate(book)
    book["briefs"] = {"unknown": "x"}
    with pytest.raises(ValueError, match=r"briefs\.unknown"):
        Phrasebook.model_validate(book)
