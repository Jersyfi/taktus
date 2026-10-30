"""The rules of a shared agent with role profiles (ADR-0163). Pure.

- `resolve` finds the profile for a caller from the roles they hold: the role they chose, the
  one role that has a profile, or — with several and no choice — the profile with the fewest
  rights.
- `held` says why a core version may not become active: a profile that would widen it, or a
  profile whose evaluation on it did not pass.
- `diagram` draws the core and each profile's differences from it (UC-4.2).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Literal

from taktus.components.catalog.domain.model.agent import (
    AgentCore,
    AgentError,
    Grants,
    RoleProfile,
    widening,
)

type Found = Literal["chosen", "only", "fewest_rights"]


def _fewer(a: Grants, b: Grants) -> bool:
    """Whether `a` holds fewer rights than `b`: a strict subset, else fewer grants, else a lower
    approval limit."""
    if a.within(b) and not b.within(a):
        return True
    if b.within(a) and not a.within(b):
        return False
    if a.size != b.size:
        return a.size < b.size
    return (a.approval_limit or 0) < (b.approval_limit or 0)


def resolve(
    profiles: Sequence[RoleProfile], roles: Collection[str], chosen: str | None = None
) -> tuple[RoleProfile, Found]:
    """The profile a caller holding `roles` is served under, and how it was found. A caller
    with no role that has a profile is refused: the core is never served unnarrowed."""
    active = {p.role: p for p in profiles if p.active}
    if chosen is not None:
        if chosen not in roles:
            raise AgentError("not_held", f"the caller does not hold the role {chosen!r}")
        if chosen not in active:
            raise AgentError("no_profile", f"the role {chosen!r} has no profile of this agent")
        return active[chosen], "chosen"
    held = [active[role] for role in sorted(set(roles)) if role in active]
    if not held:
        raise AgentError("no_profile", "none of the caller's roles has a profile of this agent")
    if len(held) == 1:
        return held[0], "only"
    least = held[0]
    for candidate in held[1:]:
        if _fewer(candidate.grants, least.grants):
            least = candidate
    return least, "fewest_rights"


def held(core: AgentCore, profiles: Sequence[RoleProfile]) -> list[str]:
    """Why the core may not become active: every active profile narrows it, and every active
    profile's evaluation on it passed (UC-8.11 §2). Empty when it may."""
    findings: list[str] = []
    for profile in sorted((p for p in profiles if p.active), key=lambda p: p.role):
        wider = widening(profile.grants, core.grants)
        if wider:
            findings.append(f"{profile.id} would grant more than {core.id}: {'; '.join(wider)}")
        verdict = core.verdicts.get(profile.id)
        if verdict != "passed":
            findings.append(
                f"the evaluation of {profile.id} on {core.id} is "
                f"{'not done' if verdict is None else verdict}"
            )
    return findings


def _listed(items: Collection[str]) -> str:
    return ", ".join(sorted(items)) or "none"


def diagram(core: AgentCore, profiles: Sequence[RoleProfile]) -> str:
    """A Mermaid flowchart: the core with its grants, and each active profile with only what
    differs from the core — what it leaves out, its limit, its tone (UC-8.11, UC-4.2)."""
    grants = core.grants
    lines = [
        "flowchart TD",
        f'  core["{core.id}<br/>flow: {core.flow}<br/>level {core.autonomy_level}'
        f"<br/>tools: {_listed(grants.tools)}<br/>connectors: {_listed(grants.connectors)}"
        f'<br/>sources: {_listed(grants.sources)}"]',
    ]
    for index, profile in enumerate(
        sorted((p for p in profiles if p.active), key=lambda p: p.role)
    ):
        mine = profile.grants
        differences = []
        for field in ("tools", "connectors", "sources", "formats"):
            left = set(getattr(grants, field)) - set(getattr(mine, field))
            if left:
                differences.append(f"without {field}: {_listed(left)}")
        if mine.approval_limit != grants.approval_limit:
            differences.append(f"approves up to {mine.approval_limit or 'nothing'}")
        if profile.tone:
            differences.append(f"tone: {profile.tone}")
        if profile.vocabulary:
            differences.append(f"vocabulary: {', '.join(profile.vocabulary)}")
        body = "<br/>".join([profile.id, *(differences or ["as the core"])])
        lines.append(f'  p{index}["{body}"]')
        lines.append(f"  core --> p{index}")
    return "\n".join(lines)
