"""The frame of an outward message (ADR-0142, UC-7.6).

A connector step that delivers what a model drafted is a **message step**. Before it sends, the
run holds it to its frame, by rule: every named check holds; a step of its own, the independent
check, answered `send`; a message that promises a date, a feature or legal advice, or that
cannot be classified, and one to more recipients than the tenant's limit, wait for a person; a
person who answered in the case stops it; the tenant's delay and quiet hours hold it; the
tenant's label is added to its text. What is sent is recorded with the case, the checks and the
label.

What the process alone tells is told before a run starts (`findings`). Everything else is told
at the step boundary from the results before it, and the tenant's rules.

Pure: no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Set
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from taktus.components.run.domain.model.work import Message, references
from taktus.components.run.ports.messages import MessageRules, QuietHours
from taktus.shared.v1 import Anchor, Method, StepId

HELD = "message.held"
"""A message step that sent nothing, with the reason as outcome: one of the tokens below."""
DELAYED = "message.delayed"
"""A message held at its boundary until its delay passes or its tenant's quiet hours end."""
SENT = "message.sent"
"""A message sent: beside its egress entry, with its record's digest in `content_digest`."""

UNDECLARED = "undeclared"
"""A delivery a model drafted that declares no message frame."""
CHECKS = "checks"
"""A named check did not hold."""
REJECTED = "rejected"
"""The independent check did not answer `send`."""
UNLABELLED = "unlabelled"
"""A message a model drafted, and the tenant configured no label."""
ANSWERED = "answered"
"""A person answered in the case."""
DELAY = "delay"
QUIET_HOURS = "quiet_hours"

SHIPPED = MessageRules(label=None, delay_seconds=600, quiet=None, recipient_limit=10)
"""The rules a tenant holds that configured none (NTC-0234): no label — so no message a model
wrote is sent — ten minutes' delay, no quiet hours, ten recipients."""

SEND = "send"
REJECT = "reject"
NO_PROMISE = "none"
PROMISES = frozenset({"date", "feature", "legal_advice"})
"""What a classification may name as a promise (UC-03 §6)."""


def drafting(
    step: StepId, values: Mapping[StepId, list[Any]], methods: Mapping[StepId, Method]
) -> frozenset[StepId]:
    """The steps of method `llm` whose answers the step's work reads through `$from`, directly
    or through steps that are not `llm` steps themselves. `values` are each step's untyped
    work values."""
    found: set[StepId] = set()
    seen: set[StepId] = set()
    pending = [r for v in values.get(step, ()) for r in references(v)]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if methods.get(current) is Method.LLM:
            found.add(current)
            continue
        pending.extend(r for v in values.get(current, ()) for r in references(v))
    return frozenset(found)


def findings(
    message: Message,
    *,
    ancestors: Set[StepId],
    drafts: Set[StepId],
    checked_reads: Set[StepId],
    connector_steps: Set[StepId],
) -> list[str]:
    """Why a message step's frame cannot hold, as far as the process alone tells, or nothing.
    `ancestors` are the steps the message step depends on, directly or through others;
    `drafts` its drafting steps; `checked_reads` the steps the check step reads through
    `$from`; `connector_steps` the steps that call a connector."""
    found: list[str] = []
    checker = message.check
    if checker not in ancestors:
        found.append(f"message.check: {checker} is not a step the message step depends on")
    if message.classification is not None and message.classification not in ancestors:
        found.append(
            f"message.classification: {message.classification} is not a step the message step "
            "depends on"
        )
    if checker in drafts:
        found.append(
            f"message.check: {checker} drafted the message, and a draft is checked by a "
            "step of its own"
        )
    for read in sorted(checked_reads):
        if read not in drafts and read not in connector_steps:
            found.append(
                f"message.check: {checker} reads {read}, and the independent check reads "
                "only the draft and the raw results of tools"
            )
    return found


def answer_of(result: Any) -> Any:
    """What a step answered: the text of an `llm` step's result, any other result as it is."""
    if isinstance(result, Mapping) and isinstance(result.get("text"), str):
        return result["text"]
    return result


def verdict(answer: Any) -> str | None:
    """The independent check's answer read by rule: `send`, `reject`, or None for an answer
    that is neither."""
    answer = answer_of(answer)
    if not isinstance(answer, str):
        return None
    read = answer.strip().lower()
    return read if read in (SEND, REJECT) else None


def promised(answer: Any) -> frozenset[str] | None:
    """What a classification names as promised: nothing for `none` alone, or the promises it
    names; None for an answer that cannot be read — which is held as if it promised."""
    answer = answer_of(answer)
    if not isinstance(answer, str) and not (
        isinstance(answer, list | tuple) and all(isinstance(a, str) for a in answer)
    ):
        return None
    words = answer if isinstance(answer, list | tuple) else re.split(r"[\s,;]+", answer)
    read = {w.strip().lower() for w in words if w.strip()}
    if read == {NO_PROMISE}:
        return frozenset()
    if read and read <= PROMISES:
        return frozenset(read)
    return None


def count(recipients: Any) -> int | None:
    """How many recipients an outward step addresses: one where it names none, a list by its
    distinct items, a text as one, a count as given; None for a value that cannot be counted."""
    if recipients is None:
        return 1
    if isinstance(recipients, bool):
        return None
    if isinstance(recipients, int):
        return recipients if recipients >= 0 else None
    if isinstance(recipients, str):
        return 1 if recipients.strip() else None
    if isinstance(recipients, list | tuple):
        try:
            return len({_key(item) for item in recipients})
        except TypeError:
            return None
    return None


def _key(item: Any) -> Any:
    if isinstance(item, Mapping):
        return tuple(sorted((str(k), _key(v)) for k, v in item.items()))
    if isinstance(item, list | tuple):
        return tuple(_key(i) for i in item)
    hash(item)
    return item


def promise_anchor(capability: str, promises: frozenset[str] | None) -> Anchor:
    """The frame's anchor on a message that promises, or cannot be classified: no tenant
    configuration names it, and none removes it."""
    what = (
        "a message that cannot be classified as promising nothing"
        if promises is None
        else "a message that promises " + ", ".join(sorted(promises)).replace("_", " ")
    )
    return Anchor.model_validate(
        {
            "id": "anc-promise",
            "class": "legal",
            "act": f"send {what} through {capability} (UC-7.6, ADR-0142)",
            "applies_to": {"actions": [capability]},
            "decider": {"role": "owner"},
        }
    )


def mass_anchor(capability: str, recipients: int | None, limit: int) -> Anchor:
    """The frame's anchor on an outward step to more recipients than the tenant's limit."""
    many = "recipients that cannot be counted" if recipients is None else f"{recipients} recipients"
    return Anchor.model_validate(
        {
            "id": "anc-mass-sending",
            "class": "legal",
            "act": f"act outward through {capability} to {many}, above the tenant's limit of "
            f"{limit} (UC-7.6, ADR-0142)",
            "applies_to": {"actions": [capability]},
            "decider": {"role": "owner"},
        }
    )


def over_limit(recipients: int | None, limit: int) -> bool:
    return recipients is None or recipients > limit


def labelled(input: Mapping[str, Any], field: str, label: str) -> dict[str, Any] | None:
    """The input with the label added to its text field as a paragraph of its own, or None
    where the field holds no text. A text that already ends with the label keeps it once."""
    text = input.get(field)
    if not isinstance(text, str):
        return None
    if text.rstrip().endswith(label):
        return dict(input)
    return {**input, field: f"{text.rstrip()}\n\n{label}"}


def zone(name: str) -> tzinfo:
    """The zone of quiet hours; UTC needs no time zone database."""
    if name == "UTC":
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"{name!r} is not a time zone") from error


def quiet_until(at: datetime, quiet: QuietHours | None) -> datetime | None:
    """When the quiet hours that hold `at` end, or None when `at` is outside them."""
    if quiet is None or quiet.begins == quiet.ends:
        return None
    tz = zone(quiet.zone)
    local = at.astimezone(tz)
    moment = local.time().replace(tzinfo=None)
    day: date = local.date()
    if quiet.begins < quiet.ends:
        inside = quiet.begins <= moment < quiet.ends
    else:
        inside = moment >= quiet.begins or moment < quiet.ends
        if moment >= quiet.begins:
            day = day + timedelta(days=1)
    if not inside:
        return None
    return _at(day, quiet.ends, tz)


def _at(day: date, moment: time, tz: tzinfo) -> datetime:
    return datetime.combine(day, moment, tzinfo=tz).astimezone(UTC)


def send_at(
    approved: datetime, delay_seconds: int, quiet: QuietHours | None
) -> tuple[datetime, str]:
    """When a message approved at `approved` is sent: after its delay, at the first moment
    outside the quiet hours; and which of the two held it last."""
    moment = approved + timedelta(seconds=delay_seconds)
    ends = quiet_until(moment, quiet)
    if ends is not None:
        return ends, QUIET_HOURS
    return moment, DELAY


def record(
    *,
    case: str | None,
    checks: Mapping[str, bool],
    check: StepId | None,
    verdict: str | None,
    classification: StepId | None,
    promises: frozenset[str] | None,
    recipients: int | None,
    label: str | None,
    drafted: bool,
) -> dict[str, Any]:
    """What `message.sent` names by digest: the case, the checks and the label (UC-7.6 §2)."""
    return {
        "case": case,
        "checks": dict(sorted(checks.items())),
        "check": None if check is None else {"step": check, "verdict": verdict},
        "classification": None
        if classification is None
        else {"step": classification, "promises": None if promises is None else sorted(promises)},
        "recipients": recipients,
        "label": label,
        "drafted_by_model": drafted,
    }
