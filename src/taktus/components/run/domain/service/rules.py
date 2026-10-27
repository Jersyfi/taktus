"""The built-in rules a `rule` step can evaluate. Pure: bytes and values in, a value out."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from string import Template
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed
from taktus.components.run.domain.model.work import (
    CLASSES,
    BacklogRule,
    CheckRule,
    ClassificationRule,
    CommitTitleRule,
    Condition,
    ConstantRule,
    Expectation,
    ExtractRule,
    ReadyRule,
    RoadmapRule,
    SpamRule,
    TemplateRule,
    VerifyArtifactRule,
    select,
)
from taktus.components.run.domain.service import ready as standard
from taktus.components.run.domain.service import roadmap as plan
from taktus.shared.v1 import Artifact


def constant(rule: ConstantRule) -> Any:
    return rule.value


def verify_artifact(
    rule: VerifyArtifactRule, artifact: Artifact | None, content: bytes | None
) -> str:
    """The artifact's text, once its bytes hash to the announced digest and match the pattern.
    Anything else is RuleFailed: nothing leaves the step, and the run goes to a person."""
    if artifact is None:
        raise RuleFailed(f"step {rule.step!r} produced no artifact {rule.artifact!r}")
    if content is None:
        raise RuleFailed(f"the content of artifact {rule.artifact!r} is not available")
    actual = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual != artifact.digest:
        raise RuleFailed(
            f"artifact {rule.artifact!r} hashes to {actual[:19]}…, not the announced "
            f"{artifact.digest[:19]}…"
        )
    text = content.decode("utf-8", errors="replace").strip()
    if rule.pattern is not None and re.search(rule.pattern, text) is None:
        raise RuleFailed(f"artifact {rule.artifact!r} does not match {rule.pattern!r}")
    return text


def check(rule: CheckRule, values: list[Any]) -> list[Any]:
    """The values, once every condition holds over its resolved value. The first condition
    that does not hold is the failure, named by its position and what was found."""
    for position, (condition, value) in enumerate(zip(rule.conditions, values, strict=True)):
        if (why := _violated(condition, value)) is not None:
            raise RuleFailed(f"condition {position + 1} does not hold: {why}")
    return values


def unheld(conditions: tuple[Condition, ...], values: list[Any]) -> str | None:
    """Why a step's `when` does not hold — the first condition that does not, by its position
    and what was found — or None when every one holds (ADR-0088). Not a failure: a step whose
    condition does not hold is skipped."""
    for position, (condition, value) in enumerate(zip(conditions, values, strict=True)):
        if (why := _violated(condition, value)) is not None:
            return f"condition {position + 1} does not hold: {why}"
    return None


def ready(rule: ReadyRule, issue: Any, open_records: Any, open_issues: Any) -> dict[str, Any]:
    """The ready standard over one issue's reading (`domain.service.ready`), once the rule's
    expectation holds; every reason it does not hold is the failure."""
    if not isinstance(issue, Mapping) or not isinstance(issue.get("number"), int):
        raise RuleFailed("the issue is not a reading with a number")
    records = standard.open_records(_names(open_records, "name"))
    issues = {int(n) for n in _names(open_issues, "number")}
    reasons = standard.admission(issue, records, issues, handed=rule.handed)
    missing = standard.missing_sections(str(issue.get("body") or ""))
    result = {
        "number": issue["number"],
        "ready": not reasons,
        "reasons": reasons,
        "missing": missing,
    }
    if rule.expect == "ready" and reasons:
        raise RuleFailed(f"issue #{issue['number']} is not ready: " + "; ".join(reasons))
    if rule.expect == "sections_missing":
        refused = [r for r in reasons if r.startswith(("not open", "a pull request"))]
        if refused:
            raise RuleFailed(f"issue #{issue['number']}: " + "; ".join(refused))
        # An issue that carries every section has nothing to refine: `missing` is empty, and
        # the steps that write sections skip themselves on it (`when`). It is no failure, and
        # it escalated ten of P-02's fourteen runs on the instance in two days.
    return result


def backlog(rule: BacklogRule, issues: Any, open_records: Any) -> dict[str, Any]:
    """The backlog in its order (`domain.service.ready.backlog`), the issues labelled `ready`
    whose content fails the standard, and both as text."""
    readings = _readings(issues)
    records = standard.open_records(_names(open_records, "name"))
    every = {int(issue["number"]) for issue in readings}
    groups = standard.backlog(readings, records, every)
    entries = [e for group in groups.values() for e in group]
    failing = sorted(
        (e for e in entries if standard.READY in e["labels"] and e["content"]),
        key=lambda e: int(e["number"]),
    )
    disagreements = [
        {"kind": "ready-fails-standard", "number": e["number"], "reasons": e["content"]}
        for e in failing
    ]
    lines: list[str] = []
    for heading, group in (
        ("Ready, in the order a session takes them", "ready"),
        ("Claimed", "claimed"),
        ("Not ready", "not_ready"),
    ):
        lines.append(f"**{heading}**")
        lines += [_entry_line(e, with_reasons=group == "not_ready") for e in groups[group]]
        if not groups[group]:
            lines.append("none")
        lines.append("")
    text = "\n".join(lines).rstrip()
    failures = "\n".join(
        f"- #{d['number']} is labelled `ready` and fails the standard: " + "; ".join(d["reasons"])
        for d in disagreements
    )
    return {
        **groups,
        "disagreements": disagreements,
        "text": text,
        "disagreements_text": failures or "none",
    }


def roadmap(rule: RoadmapRule, text: Any, issues: Any) -> dict[str, Any]:
    """The roadmap held against the open issues (`domain.service.roadmap`)."""
    if not isinstance(text, str):
        raise RuleFailed(f"the roadmap is not a text: {_short(text)}")
    found = plan.milestones(text)
    if not found:
        raise RuleFailed("the text names no milestone (### `X.Y.Z`): it is not a roadmap")
    disagreements = plan.reconcile(text, _readings(issues))
    lines = "\n".join(f"- {plan.describe(d)}" for d in disagreements)
    return {
        "milestones": [m["milestone"] for m in found],
        "disagreements": disagreements,
        "disagreements_text": lines or "none",
    }


def _readings(items: Any) -> list[Mapping[str, Any]]:
    """Issue readings, each an object with a whole number."""
    if not isinstance(items, list | tuple):
        raise RuleFailed(f"expected a list of issues, found {_short(items)}")
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("number"), int):
            raise RuleFailed(f"an issue is not a reading with a number: {_short(item)}")
    return list(items)


def _entry_line(entry: Mapping[str, Any], *, with_reasons: bool) -> str:
    milestone, level = entry["milestone"] or "-", entry["priority"] or "-"
    line = f"- #{entry['number']} · {milestone} · {level} · {entry['title']}"
    if with_reasons and entry["reasons"]:
        line += " — " + "; ".join(entry["reasons"])
    return line


def _names(items: Any, key: str) -> list[Any]:
    """The values of a listing: each item itself, or its `key` where it is an object."""
    if items is None:
        return []
    if not isinstance(items, list | tuple):
        raise RuleFailed(f"expected a list, found {_short(items)}")
    return [item.get(key) if isinstance(item, Mapping) else item for item in items]


def unmet(expectation: Expectation, output: Any) -> str | None:
    """Why a reading does not show what its step expects of it, or None when it does."""
    try:
        value = select(output, expectation.select)
    except KeyError:
        return f"the reading has no {expectation.select}"
    why = _violated(
        Condition(
            value=value,
            equals=expectation.equals,
            matches=expectation.matches,
            not_matches=expectation.not_matches,
        ),
        value,
    )
    if why is None:
        return None
    if expectation.says is None:
        return f"{expectation.select}: {why}"
    return f"{_said(expectation.says, output)} ({expectation.select}: {why})"


def _said(text: str, output: Any) -> str:
    """`text` with each `${name}` replaced by that field of the reading; a name the reading
    does not carry stays as written."""
    fields = output if isinstance(output, Mapping) else {}

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in fields:
            return match.group(0)
        found = fields[name]
        return found if isinstance(found, str) else json.dumps(found, ensure_ascii=False)

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value, text)


def violated(condition: Condition, value: Any) -> str | None:
    """Why the condition does not hold over the value, or None when it holds."""
    return _violated(condition, value)


def _violated(condition: Condition, value: Any) -> str | None:
    if condition.equals is not None and value != condition.equals:
        return f"expected {_short(condition.equals)}, found {_short(value)}"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if condition.matches is not None and re.search(condition.matches, text) is None:
        return f"{_short(value)} does not match {condition.matches!r}"
    if condition.not_matches is not None and re.search(condition.not_matches, text) is not None:
        return f"{_short(value)} matches {condition.not_matches!r}, which it must not"
    return None


def spam(rule: SpamRule, text: Any) -> dict[str, Any]:
    """Whether the text matches any of the rule's patterns, searched case-blind, and which."""
    if isinstance(text, str):
        whole = text
    elif isinstance(text, list | tuple) and all(isinstance(part, str) for part in text):
        whole = "\n".join(text)
    else:
        raise RuleFailed(f"the text to screen is not a text or a list of texts: {_short(text)}")
    matched = [p for p in rule.patterns if re.search(p, whole, re.IGNORECASE) is not None]
    return {"spam": bool(matched), "matched": matched}


ANSWER_LINE = re.compile(r"^\s*(class|version|summary)\s*:\s*(.*?)\s*$", re.IGNORECASE)


def classification(
    rule: ClassificationRule, answer: Any, screened: Any, versions: Any
) -> dict[str, Any]:
    """The contribution's class: `spam` where the screen found it, otherwise what the answer
    names, held to the classes and the versions that may be answered."""
    if not isinstance(screened, Mapping) or not isinstance(screened.get("spam"), bool):
        raise RuleFailed(f"the screen is not a spam rule's result: {_short(screened)}")
    if screened["spam"]:
        matched = ", ".join(str(p) for p in screened.get("matched") or [])
        return {"class": "spam", "version": None, "summary": f"matched by rule: {matched}"}
    if isinstance(answer, Mapping) and isinstance(answer.get("text"), str):
        answer = answer["text"]  # an llm step's whole result
    if not isinstance(answer, str):
        raise RuleFailed(f"the answer is not a text: {_short(answer)}")
    fields: dict[str, str] = {}
    for line in answer.splitlines():
        if (match := ANSWER_LINE.match(line)) is not None:
            name = match.group(1).lower()
            if name in fields:
                raise RuleFailed(f"the answer names {name!r} twice")
            fields[name] = match.group(2)
    kind = fields.get("class", "").lower()
    if kind not in CLASSES:
        raise RuleFailed(
            f"the answer names no class of {', '.join(CLASSES)}: {_short(fields.get('class'))}"
        )
    if kind == "spam":
        return {"class": "spam", "version": None, "summary": fields.get("summary") or "spam"}
    allowed = [str(v) for v in _names(versions, "milestone")]
    version = fields.get("version", "").strip("`")
    if version not in allowed:
        raise RuleFailed(
            f"a {kind} names one of the versions {', '.join(allowed) or '(none)'}, "
            f"not {_short(version)}"
        )
    summary = fields.get("summary", "")
    if not summary:
        raise RuleFailed(f"a {kind} carries a summary")
    return {"class": kind, "version": version, "summary": summary}


def template(rule: TemplateRule, values: dict[str, Any]) -> str:
    """The text with every `${name}` replaced; a name without a value is the failure."""
    rendered = {
        name: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        for name, value in values.items()
    }
    try:
        return Template(rule.text).substitute(rendered)
    except (KeyError, ValueError) as error:
        raise RuleFailed(
            f"the template names {error.args[0]!r}, which the values do not carry"
        ) from error


def extract(rule: ExtractRule, values: Any, excluding: Any) -> dict[str, Any]:
    """Every distinct text the rule composes from a match among `values` that no match among
    `excluding` composes too, sorted (ADR-0095)."""
    pattern = re.compile(rule.pattern)
    found = _composed(rule, pattern, values, "values")
    left_out = _composed(rule, pattern, excluding, "excluding")
    return {"extracted": sorted(found - left_out)}


def _composed(rule: ExtractRule, pattern: re.Pattern[str], items: Any, what: str) -> set[str]:
    composed: set[str] = set()
    for text in _texts(items, what):
        match = pattern.search(text)
        if match is not None:
            groups = {name: value or "" for name, value in match.groupdict().items()}
            composed.add(Template(rule.text).substitute(groups))
    return composed


def _texts(items: Any, what: str) -> list[str]:
    """The texts of a list: its strings, the `path` or else the `name` of its entries, and the
    same of every list nested in it. Nothing given is nothing."""
    if items is None:
        return []
    if not isinstance(items, list | tuple):
        raise RuleFailed(f"{what} is not a list: {_short(items)}")
    texts: list[str] = []
    for item in items:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, list | tuple):
            texts.extend(_texts(item, what))
        elif isinstance(item, Mapping) and isinstance(item.get("path", item.get("name")), str):
            texts.append(str(item.get("path", item.get("name"))))
        else:
            raise RuleFailed(
                f"an item of {what} is neither a text nor an entry with a path or a name: "
                f"{_short(item)}"
            )
    return texts


CONVENTIONAL = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()]*)\))?(?P<breaking>!)?: (?P<summary>\S.*)$"
)
"""A sentence already in the Conventional Commits form: a type, a scope, a summary."""

SCOPE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
"""A scope the title keeps: lower-case words, joined without spaces."""


def commit_title(
    rule: CommitTitleRule,
    title: Any,
    number: Any,
    labels: Any,
    files: Any,
    proposal: Any,
) -> dict[str, Any]:
    """The title in the Conventional Commits form, its type from the first source that gives
    one: the sentence, a label, the changed files, the proposal (ADR-0101)."""
    if not isinstance(title, str) or not title.strip():
        raise RuleFailed(f"the title is not a sentence: {_short(title)}")
    sentence = " ".join(title.split())
    formed = CONVENTIONAL.match(sentence)
    scope: str | None = None
    kind: str | None
    if formed is not None and formed.group("type") in rule.types:
        kind, source = formed.group("type"), "title"
        scope = formed.group("scope")
        summary = formed.group("summary")
        bang = formed.group("breaking") or ""
    else:
        bang = ""
        summary = _summary(sentence)
        kind, source = _labelled(rule, labels), "labels"
        if kind is None:
            kind, source = _by_files(rule, files), "files"
        proposed = _proposed(rule, proposal)
        if kind is None and proposed is not None:
            kind, source = proposed[0], "proposal"
        if proposed is not None:
            scope = proposed[1]
        if kind is None:
            raise RuleFailed(
                "no type for the title: the sentence is not in the form, no label names one, "
                "the files changed do not decide it, and the proposal names none of "
                + ", ".join(rule.types)
            )
    if scope is not None and SCOPE.match(scope) is None:
        scope = None
    head = f"{kind}({scope})" if scope else kind
    return {
        "title": f"{head}{bang}: {summary} (#{number})",
        "type": kind,
        "scope": scope,
        "source": source,
    }


def _summary(sentence: str) -> str:
    """The sentence as a summary: a final full stop dropped, the first letter lower-cased
    unless the first word is an abbreviation — `CI`, `P-03`, a capital and more capitals or
    digits — that keeps its capitals."""
    text = sentence[:-1] if sentence.endswith(".") else sentence
    first = text.split(" ", 1)[0]
    if any(c.isupper() or c.isdigit() for c in first[1:]) or not first[:1].isupper():
        return text
    return text[0].lower() + text[1:]


def _labelled(rule: CommitTitleRule, labels: Any) -> str | None:
    if rule.label_pattern is None:
        return None
    pattern = re.compile(rule.label_pattern)
    named = sorted(
        {
            match.group("type")
            for label in _texts(labels, "labels")
            if (match := pattern.search(label)) is not None and match.group("type") in rule.types
        }
    )
    if len(named) > 1:
        raise RuleFailed(f"the labels name more than one type: {', '.join(named)}")
    return named[0] if named else None


def _by_files(rule: CommitTitleRule, files: Any) -> str | None:
    paths = _texts(files, "files")
    if not paths:
        return None
    for entry in rule.by_files:
        pattern = re.compile(entry.pattern)
        if all(pattern.search(path) is not None for path in paths):
            return entry.type
    return None


def _proposed(rule: CommitTitleRule, proposal: Any) -> tuple[str | None, str | None] | None:
    """The type and scope the proposal names; the type None where it is not among the types."""
    if rule.proposed is None or not isinstance(proposal, str):
        return None
    match = re.search(rule.proposed, proposal)
    if match is None:
        return None
    kind = match.group("type")
    scope = match.groupdict().get("scope")
    return (kind if kind in rule.types else None), scope


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return repr(text if len(text) <= 80 else text[:77] + "…")
