"""The built-in rules a `rule` step can evaluate. Pure: bytes and values in, a value out."""

from __future__ import annotations

import hashlib
import json
import re
from string import Template
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed
from taktus.components.run.domain.model.work import (
    CheckRule,
    Condition,
    ConstantRule,
    TemplateRule,
    VerifyArtifactRule,
)
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
