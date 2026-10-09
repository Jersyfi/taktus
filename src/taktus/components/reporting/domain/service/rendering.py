"""The renderings of a report, and every sentence said back in the channel. Pure.

**Composed from the record, and from nothing else.** Each rendering takes the report — the
record the ledger entry points to (ADR-0006) — and lays out the same identifier, the same items
and the same date. None of them adds a fact the others lack, so they cannot disagree:

- `repository_text` — **English**, as everything in a repository is, and minimal: what future
  work needs. It names where an answer was given — the channel, the address, the
  thread — and never what was said there.
- `message` — **in the owner's language**, from the tenant's phrasebook, with every link the
  report concerns. It never quotes what anyone wrote in the channel.
- the view is the read side's (`application/query/reports.py`): the report itself, with its
  deliveries and its history.
"""

from __future__ import annotations

from taktus.components.reporting.domain.model import (
    DeliveryState,
    OwnerChannel,
    Phrasebook,
    Reading,
    Report,
    ReportKind,
)

KIND_IN_THE_REPOSITORY: dict[ReportKind, str] = {
    ReportKind.DECISION: "Decision request",
    ReportKind.NEED: "Needs request",
    ReportKind.DATE: "Date",
    ReportKind.FAILURE: "Failure",
}


def view_url(channel: OwnerChannel, report_id: str) -> str | None:
    """Where the report's view is read, when the control plane's address is configured."""
    if channel.view_base is None:
        return None
    return f"{channel.view_base.rstrip('/')}/owner/reports/{report_id}"


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


def message(report: Report, channel: OwnerChannel) -> str:
    """The report as a message in the owner's channel, in the owner's language."""
    book = channel.phrasebook
    heading = {
        ReportKind.DECISION: book.decision,
        ReportKind.NEED: book.need,
        ReportKind.DATE: book.date,
        ReportKind.FAILURE: book.failure,
    }[report.kind]
    lines = [
        f"*{heading}: {report.title}* ({report.id})",
        "",
        f"{book.needed}:",
        *(f"• {item}" for item in report.needed),
        "",
        f"{book.steps}:",
        *(f"{n}. {step}" for n, step in enumerate(report.steps, start=1)),
        "",
        f"{book.standing_still}:",
        *(f"• {item}" for item in report.standing_still),
        "",
        f"{book.due}: {report.due.isoformat()}",
    ]
    links = [f"• {link.label}: {link.url}" for link in report.links]
    task = report.task()
    if task is not None and task.url is not None:
        links.append(f"• {book.task}: {task.url}")
    view = view_url(channel, report.id)
    if view is not None:
        links.append(f"• {book.view}: {view}")
    if links:
        lines += ["", f"{book.links}:", *links]
    lines += ["", book.answer_with.format(answers=answers(report, book))]
    return "\n".join(lines)


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
