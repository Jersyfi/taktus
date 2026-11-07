"""The rules of a shared agent with role profiles (ADR-0163). Pure.

- `resolve` finds the profile for a caller from the roles they hold: the role they chose, the
  one role that has a profile, or — with several and no choice — the profile with the fewest
  rights.
- `held` says why a core version may not become active: a profile that would widen it, or a
  profile whose evaluation on it did not pass.
- `diagram` draws the core and each profile's differences from it (UC-4.2).
- `describe` says in plain language what the agent does, what it reads, which tools it may use
  and what it must not do, from its version alone (UC-8.7, ADR-0287).
- `named_by_product` finds a tool, a source or a connector named after a product rather than
  by what it does (ADR-0003).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from typing import Literal

from taktus.components.catalog.domain.model.agent import (
    AgentCore,
    AgentError,
    Grants,
    RoleProfile,
    widening,
)
from taktus.shared.v1.capability import CAPABILITY_PATTERN

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


LEVELS = {
    1: "it observes and proposes; a person decides and acts",
    2: "it acts only after a person approved each step",
    3: "it acts on its own under supervision; a person watches its reports and samples",
    4: "it acts on its own within its frame; a person is drawn in when the frame is exceeded",
}
"""What each autonomy level means for what the agent may do on its own (ADR-0026)."""


def describe(core: AgentCore, profiles: Sequence[RoleProfile]) -> str:
    """The agent in plain language, generated from its core and its active profiles and never
    stored apart from them: what it does, what it reads, which tools it may use, and what it
    must not do (UC-8.7 §2)."""
    grants = core.grants
    level = int(core.autonomy_level)
    lines = [f"# {core.agent} — version {core.version}", "", "## What it does", ""]
    lines.append(f"{core.purpose.strip()} It runs the process `{core.flow}`.")
    if core.model is not None:
        lines.append(f"It asks a model of the purpose `{core.model}`.")
    lines.append(f"At autonomy level {level} {LEVELS[level]}.")
    if core.autonomy_reason is not None:
        lines.append(f"The level was chosen because: {core.autonomy_reason.strip()}")
    lines += ["", "## What it reads", ""]
    lines.append(_sentence("Knowledge sources", grants.sources))
    lines.append(_sentence("Connectors", grants.connectors))
    lines += ["", "## Which tools it may use", ""]
    lines.append(_sentence("Tools", grants.tools))
    if grants.formats:
        lines.append(_sentence("Output formats", grants.formats))
    lines += ["", "## What it must not do", ""]
    lines.append(
        "- use any tool, read any source or call any connector not named above;"
        if grants.size
        else "- use any tool, read any source or call any connector: it is granted none;"
    )
    lines.append(f"- act above autonomy level {level}, whoever calls it;")
    lines.append(
        "- approve any amount on its own;"
        if grants.approval_limit is None
        else f"- approve an amount above {grants.approval_limit} on its own;"
    )
    lines.append(
        "- act with its author's credential: every call acts with its caller's own (ADR-0247)."
    )
    active = sorted((p for p in profiles if p.active), key=lambda p: p.role)
    if active:
        lines += ["", "## By role", ""]
        for profile in active:
            lines.append(f"- **{profile.role}** (`{profile.id}`): {_narrowed(grants, profile)}.")
    return "\n".join(lines) + "\n"


def named_by_product(grants: Grants, products: Collection[str]) -> list[str]:
    """Each tool that is no capability, and each tool, source or connector one of whose
    segments is a product's name, as a finding; empty where everything is named by function
    (ADR-0003). `products` is the composition's to give: the names of adapters that are not
    themselves the name of a capability."""
    found: list[str] = []
    shape = re.compile(CAPABILITY_PATTERN)
    for tool in grants.tools:
        if not shape.match(tool):
            found.append(f"the tool {tool!r} is no capability: lowercase dotted segments")
    named = {name.lower() for name in products}
    for field, noun in (("tools", "tool"), ("sources", "source"), ("connectors", "connector")):
        for value in getattr(grants, field):
            hit = sorted(set(re.split(r"[.:_-]", value.lower())) & named)
            if hit:
                found.append(
                    f"the {noun} {value!r} names the product {hit[0]!r}; name what it does"
                )
    return found


def _narrowed(core: Grants, profile: RoleProfile) -> str:
    mine = profile.grants
    said: list[str] = []
    for field, noun in (
        ("tools", "tool"),
        ("sources", "source"),
        ("connectors", "connector"),
        ("formats", "format"),
    ):
        left = sorted(set(getattr(core, field)) - set(getattr(mine, field)))
        if left:
            said.append(f"no {noun} {', '.join(left)}")
    if mine.approval_limit != core.approval_limit:
        said.append(
            "approves nothing"
            if mine.approval_limit is None
            else f"approves up to {mine.approval_limit}"
        )
    return "; ".join(said) if said else "the core as it is"


def _sentence(label: str, values: Collection[str]) -> str:
    return f"{label}: {', '.join(sorted(values)) if values else 'none'}."
