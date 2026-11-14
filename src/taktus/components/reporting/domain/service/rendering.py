"""The renderings of a report, and every sentence said back in the channel. Pure.

**Composed from the record, and from nothing else.** Each rendering takes the report — the
record the ledger entry points to (ADR-0006) — and lays out the same identifier, the same items
and the same date. None of them adds a fact the others lack, so they cannot disagree:

- `repository_text` — **English**, as everything in a repository is, and minimal: what future
  work needs. It names where an answer was given — the channel, the address, the
  thread — and never what was said there.
- `message` — **in the owner's language**, from the tenant's phrasebook: the report's short
  form (ADR-0316). One headline, what is needed from the reader, the date, every address the
  report concerns and the link to its view. The record's own sentences appear only as quotes of
  one line. It never quotes what anyone wrote in the channel.
- the view is the read side's (`application/query/reports.py`): the report itself, with its
  deliveries and its history.

`shown` lays out a level of a live representation for a channel that cannot draw it: the
level's own text equivalent and the link to it in the web app (ADR-0069).
"""

from __future__ import annotations

from urllib.parse import quote

from taktus.components.reporting.domain.model import (
    DeliveryState,
    OwnerChannel,
    Phrasebook,
    Reading,
    Report,
    ReportKind,
    Said,
)
from taktus.components.reporting.domain.service.levels import (
    OriginLevel,
    OverviewLevel,
    ProcessLevel,
    RunLevel,
)
from taktus.components.reporting.domain.service.reports import Composed, Item

type Level = OverviewLevel | ProcessLevel | RunLevel | OriginLevel

KIND_IN_THE_REPOSITORY: dict[ReportKind, str] = {
    ReportKind.DECISION: "Decision request",
    ReportKind.NEED: "Needs request",
    ReportKind.DATE: "Date",
    ReportKind.FAILURE: "Failure",
    ReportKind.SIGNALS: "Daily signals",
}


def view_url(channel: OwnerChannel, report_id: str) -> str | None:
    """Where the report's view is read, when the control plane's address is configured: the
    report's page in the web app, under the reader's sign-in (DEC-0218, ADR-0120). Its route
    is the part after `#`, as `web/src/lib/links.ts` builds it."""
    if channel.view_base is None:
        return None
    return f"{channel.view_base.rstrip('/')}/app/#/reports/{quote(report_id, safe='')}"


def repository_text(report: Report) -> str:
    """The report as a record in a repository: English, minimal, durable."""
    lines = [
        f"# {report.id} — {report.title}",
        "",
        f"**Kind:** {KIND_IN_THE_REPOSITORY[report.kind]}",
        f"**Needed by:** {report.due.isoformat()}",
        f"**State:** {report.state}",
        "",
        "## What is needed",
        "",
        *(f"- {item}" for item in report.needed),
        "",
        "## Steps",
        "",
        *(f"{n}. {step}" for n, step in enumerate(report.steps, start=1)),
        "",
        "## What stands still",
        "",
        *(f"- {item}" for item in report.standing_still),
        "",
        "## Answers offered",
        "",
        *(
            f"- {o.id}: {o.label}" + (" (recommended)" if o.recommended else "")
            for o in report.offered
        ),
    ]
    if report.links:
        lines += ["", "## Links", "", *(f"- {link.label}: {link.url}" for link in report.links)]
    if report.deliveries:
        lines += ["", "## Delivery", ""]
        for d in report.deliveries:
            line = f"- {d.channel} {d.state} {d.at.date().isoformat()}"
            if d.state is not DeliveryState.DELIVERED and d.reason is not None:
                line += f": {d.reason}"
            if d.url is not None:
                line += f": {d.url}"
            elif d.record is not None:
                line += f": {d.record}"
            lines.append(line)
    if report.filed is not None:
        filed = report.filed
        lines += [
            "",
            "## Answer",
            "",
            f"- {filed.answer}, confirmed {filed.at.date().isoformat()}",
        ]
        if filed.record is not None:
            lines.append(f"- filed as {filed.record}")
        if filed.where is not None:
            lines.append(f"- given at {filed.where}")
    return "\n".join(lines) + "\n"


def answers(report: Report, book: Phrasebook) -> str:
    """The answers a person may give, as they type them."""
    if report.kind is ReportKind.DECISION:
        return ", ".join(
            o.id + (f" ({book.recommended})" if o.recommended else "") for o in report.offered
        )
    return ", ".join(o.label for o in report.offered)


QUOTE = 100
"""The longest quote of a message, in characters: one line of the record's text (ADR-0316)."""
OPTION = 60
"""The longest option of a decision request in a message: its proposal, in a few words."""
LISTED = 8
"""The most lines of a list a message carries; the rest are counted and linked."""
ASKS_FOR_ITEMS = (ReportKind.DECISION, ReportKind.NEED, ReportKind.DATE)
"""The kinds whose message carries each needed item (UC-6.11 §2)."""


def one_line(text: str, limit: int = QUOTE) -> str:
    """The text on one line, cut at `limit` characters with an ellipsis."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _absolute(url: str) -> bool:
    return url.startswith(("https://", "http://"))


def _said(book: Phrasebook, said: Said) -> str | None:
    return book.brief(said.entry, said.values)


def message(report: Report, channel: OwnerChannel) -> str:
    """The report as a message in the owner's channel, in the owner's language: its short form
    (ADR-0316 §2). One headline; what is needed from the reader; a quote of one line where the
    event has one; the date; one link to the report's page, which holds the full record; the
    answer line. The repository text and the view keep everything else."""
    book = channel.phrasebook
    heading = {
        ReportKind.DECISION: book.decision,
        ReportKind.NEED: book.need,
        ReportKind.DATE: book.date,
        ReportKind.FAILURE: book.failure,
        ReportKind.SIGNALS: book.signals,
    }[report.kind]
    brief = report.brief
    headline = None if brief is None else _said(book, brief.headline)
    lines: list[str] = []
    if headline is not None:
        lines.append(f"*{headline if heading is None else f'{heading}: {headline}'}*")
    elif heading is not None:
        # Without a brief the title is the record's own text: set apart as a quote.
        lines += [f"*{heading}*", f"> {one_line(report.title)}"]
    else:
        lines.append(f"> {one_line(report.title)}")
    if brief is not None and brief.quote is not None:
        lines.append(f"> {one_line(brief.quote)}")
    if report.kind in ASKS_FOR_ITEMS:
        lines += [f"> {one_line(item)}" for item in report.needed]
    if report.kind is ReportKind.DECISION:
        lines += [f"> {o.id}: {one_line(o.label, OPTION)}" for o in report.offered]
    listed: set[str] = set()
    if brief is not None and brief.items:
        for item in brief.items[:LISTED]:
            text = _said(book, item)
            if text is None:
                continue
            lines.append(" ".join(("•", text, *item.links)))
        listed = {link for item in brief.items for link in item.links}
        rest = len(brief.items) - LISTED
        more = book.brief("more", {"count": str(rest)}) if rest > 0 else None
        if more is not None:
            lines.append(f"• {more}")
    ask = None if brief is None or brief.ask is None else _said(book, brief.ask)
    if ask is not None:
        lines.append(ask)
    lines.append(f"{book.due}: {report.due.isoformat()}")
    concerns = [link.url for link in report.links if _absolute(link.url) and link.url not in listed]
    if concerns:
        lines.append(f"{book.links}: " + " · ".join(concerns))
    task = report.task()
    if task is not None and task.url is not None:
        lines.append(f"{book.task}: {task.url}")
    view = view_url(channel, report.id)
    lines.append(f"{book.view}: {view}" if view is not None else f"({report.id})")
    lines.append(book.answer_with.format(answers=answers(report, book)))
    return "\n".join(lines)


def role_message(composed: Composed, reader: str, channel: OwnerChannel) -> str | None:
    """A role's scheduled report as a message in the tenant's language (ADR-0316 §5): one
    headline, then one line for each item that bears on the reader, with its link. None where
    the phrasebook has no short form; the report's own lines are said then."""
    book = channel.phrasebook
    if composed.quiet:
        return book.brief("role_quiet", {"role": reader})
    headline = book.brief("role_report", {"role": reader, "count": str(len(composed.items))})
    if headline is None:
        return None
    lines = [f"*{headline}*"]
    for item in composed.items[:LISTED]:
        if item.kind == "figure":
            # A figure carries its definition and its value as the reader's view has them
            # (UC-6.2 §2): the record's line, quoted.
            lines.append(f"> {one_line(item.text)}")
            continue
        said, link = _role_line(item, channel)
        if said is None:
            return None
        lines.append(" ".join(("•", said, *(() if link is None else (link,)))))
    rest = len(composed.items) - LISTED
    more = book.brief("more", {"count": str(rest)}) if rest > 0 else None
    if more is not None:
        lines.append(f"• {more}")
    overview = None if channel.view_base is None else f"{channel.view_base.rstrip('/')}/app/#/"
    if overview is not None:
        lines.append(f"{book.view}: {overview}")
    return "\n".join(lines)


def _role_line(item: Item, channel: OwnerChannel) -> tuple[str | None, str | None]:
    book = channel.phrasebook
    if item.kind == "decision":
        return book.brief("role_decision", {}), view_url(channel, item.ref)
    if item.kind == "escalation":
        return book.brief("role_escalated", dict(item.values)), run_url(channel, item.ref)
    if item.kind == "blocked":
        return book.brief("role_blocked", dict(item.values)), run_url(channel, item.ref)
    return book.brief("role_switch_off", {"process": item.ref}), None


def reflected(report: Report, reading: Reading, book: Phrasebook) -> str:
    """The one message that sends a reading back: never the answer's own words."""
    said = book.reflect.format(answer=reading.answer, label=report.offer(reading.answer).label)
    if reading.kept:
        said += " " + book.kept
    return said + " " + book.confirm.format(yes=book.yes_words[0], no=book.no_words[0])


def asked_back(report: Report, book: Phrasebook) -> str:
    return book.asked_back.format(answers=answers(report, book))


def filed(answer: str, book: Phrasebook) -> str:
    return book.filed.format(answer=answer)


def run_url(channel: OwnerChannel, run_id: str) -> str | None:
    """Where the web app draws one run, when the control plane's address is configured."""
    if channel.view_base is None:
        return None
    return f"{channel.view_base.rstrip('/')}/app/#/runs/{quote(run_id, safe='')}"


def level_url(channel: OwnerChannel, level: Level) -> str | None:
    """Where the web app draws the level live, when the control plane's address is configured:
    its route is the part after `#` (ADR-0063 §1), as `web/src/lib/links.ts` builds it. The
    overview is the web app's root route, where it starts (ADR-0067)."""
    if channel.view_base is None:
        return None
    if isinstance(level, OverviewLevel):
        route = ""
    elif isinstance(level, RunLevel):
        route = f"runs/{quote(level.run.id, safe='')}"
    elif isinstance(level, OriginLevel):
        result = level.result
        route = f"origins/{quote(result.run, safe='')}/{quote(result.step, safe='')}"
    else:
        process = level.process
        route = f"processes/{quote(process.id, safe='')}/{quote(process.version, safe='')}"
    return f"{channel.view_base.rstrip('/')}/app/#/{route}"


def shown(level: Level, channel: OwnerChannel) -> str:
    """A level for a channel that cannot draw it: its text equivalent, element by element, as
    the level hands it to the web app — never composed again — and the link to it live there
    (UC-6.10 *beyond the web app*, ADR-0069). The overview is written out in the order the web
    app writes its text: each area, then each of its processes and the steps running in it. The
    origin of a result is written as the web app writes it: its summary, the result, each step
    on its path and each source read."""
    if isinstance(level, OverviewLevel):
        lines: list[str] = []
        for area in level.areas:
            lines.append(area.text)
            for process in area.processes:
                lines.append(f"• {process.text}")
                lines += [f"• {step.text}" for step in process.running]
    elif isinstance(level, RunLevel):
        lines = [level.run.text, *(f"• {step.text}" for step in level.steps)]
    elif isinstance(level, OriginLevel):
        lines = [
            level.summary,
            f"• {level.result.text}",
            *(f"• {step.text}" for step in level.steps),
            *(f"• {source.text}" for source in level.sources),
        ]
    else:
        lines = [
            level.process.text,
            *(f"• {step.text}" for step in level.steps),
            *(f"• {run.text}" for run in level.runs),
        ]
    link = level_url(channel, level)
    if link is not None and channel.phrasebook.live is not None:
        lines += ["", f"{channel.phrasebook.live}: {link}"]
    return "\n".join(lines)
