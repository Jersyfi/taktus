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
    CheckRule,
    Condition,
    ConstantRule,
    Expectation,
    ReadyRule,
    TemplateRule,
    VerifyArtifactRule,
    select,
)
from taktus.components.run.domain.service import ready as standard
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


def ready(rule: ReadyRule, issue: Any, open_records: Any, open_issues: Any) -> dict[str, Any]:
    """The ready standard over one issue's reading (`domain.service.ready`), once the rule's
    expectation holds; every reason it does not hold is the failure."""
    if not isinstance(issue, Mapping) or not isinstance(issue.get("number"), int):
        raise RuleFailed("the issue is not a reading with a number")
    records = standard.open_records(_names(open_records, "name"))
    issues = {int(n) for n in _names(open_issues, "number")}
    reasons = standard.admission(issue, records, issues)
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
        if not missing:
            raise RuleFailed(
                f"issue #{issue['number']} carries every section already: "
                + ", ".join(f"'{name}'" for name in standard.SECTIONS)
            )
    return result


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
    return None if why is None else f"{expectation.select}: {why}"


def _violated(condition: Condition, value: Any) -> str | None:
    if condition.equals is not None and value != condition.equals:
        return f"expected {_short(condition.equals)}, found {_short(value)}"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if condition.matches is not None and re.search(condition.matches, text) is None:
        return f"{_short(value)} does not match {condition.matches!r}"
    if condition.not_matches is not None and re.search(condition.not_matches, text) is not None:
        return f"{_short(value)} matches {condition.not_matches!r}, which it must not"
    return None


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


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return repr(text if len(text) <= 80 else text[:77] + "…")
