"""Which anchors name a step's act (ADR-0042). Pure: the configuration and the step in, the
anchors that apply out.

An anchor's `applies_to` has up to three selectors. **Every selector an anchor gives must
match, and within one selector any item may.** `payment.release:*` together with the risk
class `financial.high` therefore anchors a payment release of high risk, not every payment
release and not everything of high risk — as the contract's own example reads.

- **actions** match a tool action of the step — a capability it requires, the connector
  operation it calls or waits on, that operation's capability — by capability pattern;
- **processes** match the process the run executes;
- **risk_classes** match when a tool action of the step falls under one of the classes, as the
  configuration defines them.

A capability pattern matches segment by segment. `*` as a segment matches any one segment, and
as the last segment it matches everything below (`code.*` matches `code.edit` and
`code.edit.inline`). A qualifier narrows: `vcs.push:protected` matches only that qualifier; a
pattern without one, or with `:*`, matches the capability with any qualifier or none.

Scope: an anchor's `domain` and `jurisdiction` are not evaluated until domains exist (UC-15.5).
Meanwhile such an anchor holds everywhere in the tenant: never less than configured.
"""

from __future__ import annotations

from collections.abc import Sequence

from taktus.components.governance.domain.model.anchors import AnchorConfiguration
from taktus.shared.v1 import Anchor


def matches(pattern: str, action: str) -> bool:
    """Whether a capability pattern covers a tool action."""
    pattern_base, _, pattern_qualifier = pattern.partition(":")
    action_base, _, action_qualifier = action.partition(":")
    if pattern_qualifier not in ("", "*") and pattern_qualifier != action_qualifier:
        return False
    wanted = pattern_base.split(".")
    given = action_base.split(".")
    if wanted[-1] == "*":
        if len(given) < len(wanted):
            return False
        given = given[: len(wanted) - 1]
        wanted = wanted[:-1]
    if len(wanted) != len(given):
        return False
    return all(w in ("*", g) for w, g in zip(wanted, given, strict=True))


def applies(
    anchor: Anchor,
    configuration: AnchorConfiguration,
    *,
    process: str,
    actions: Sequence[str],
) -> bool:
    selectors = anchor.applies_to
    if selectors.actions is not None and not any(
        matches(p, a) for p in selectors.actions for a in actions
    ):
        return False
    if selectors.processes is not None and process not in selectors.processes:
        return False
    if selectors.risk_classes is not None:
        covered = [
            pattern
            for risk in selectors.risk_classes
            for pattern in configuration.risk_classes.get(risk, ())
        ]
        if not any(matches(p, a) for p in covered for a in actions):
            return False
    return True


def applying(
    configuration: AnchorConfiguration, *, process: str, actions: Sequence[str]
) -> tuple[Anchor, ...]:
    """The anchors that name the step's act, in the configuration's order."""
    return tuple(
        a
        for a in configuration.anchors
        if applies(a, configuration, process=process, actions=actions)
    )
