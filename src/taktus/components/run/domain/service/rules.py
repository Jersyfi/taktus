"""The built-in rules a `rule` step can evaluate. Pure: bytes and values in, a value out."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from taktus.components.run.domain.model.errors import RuleFailed
from taktus.components.run.domain.model.work import ConstantRule, VerifyArtifactRule
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
