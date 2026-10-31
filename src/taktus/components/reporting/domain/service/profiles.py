"""A role's profile, derived from the processes it takes part in (UC-15.7, ADR-0167 §3 to §5).

For one role of the tenant's structure the profile says what the processes need of it:

- the value streams it is **responsible for**, and those it **serves** — a stream whose processes
  have a step the role performs or takes over;
- the steps it **performs** — `human` steps of the role, each with its task and expertise;
- what it must be able to **take over** — the steps whose fallback goes to the role;
- what it **decides** — the anchors whose decider is the role, and the steps whose `ask` names it;
- what it **supervises** — the checks of kind `approval` or `sampling` that name it;
- the **expertise** all of that needs;
- its **load** now and if Taktus stopped, what **waits** at it, and the decision requests open
  for it.

A step that names no role counts for `owner`, as the stage view and the value stream show it.

**No figure names a person** (principle 14). A figure that persons' work produced — the time
waited at the role, the steps of it performed — is withheld where fewer than two identities hold
the role, and says why (ADR-0015, NTC-0168). A reader who holds the role sees their own waits
beside it. What Taktus performs is the process's, and is never withheld. No field says whether a
person is needed: a workforce decision is a strategic anchor (ADR-0008).

**Not reviewed.** The profile is built before the labour-law review that DEC-0029 names. Every
profile, and its export, says so.

Pure: the facts in, the views out. Nothing is stored.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from pydantic import Field

from taktus.shared.v1 import Value

OWNER = "owner"
"""The role a person's step that names none counts for (UC-6.15, UC-15.6)."""
TOO_FEW = 2
"""Fewer identities than this hold a role: its figure would be one person's (ADR-0015)."""
SUPERVISING = frozenset({"approval", "sampling"})
"""The kinds of check a role carries out on a value (UC-4.13)."""

REVIEW = (
    "Not reviewed: built before the labour-law review that DEC-0029 names (co-determination, "
    "§87(1) no. 6 BetrVG). Not to be used before that review has covered it for the tenant's "
    "jurisdiction."
)
WORKFORCE = (
    "This profile states what the processes need of the role. Whether a person is needed, how "
    "many or which one, is not its question: a workforce decision stays a strategic anchor."
)


def withheld_reason(role: str) -> str:
    return (
        f"withheld: fewer than {TOO_FEW} identities hold the role {role}, so the figure would be "
        "one person's (ADR-0015)"
    )


# --- the facts, as the composition hands them over -----------------------------------------


class CheckFacts(Value):
    kind: str = Field(min_length=1)
    role: str | None = None


class StepFacts(Value):
    """One step of an active version, as far as a person acts at it."""

    id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    role: str | None = None
    expertise: tuple[str, ...] = ()
    task: str | None = None
    """What a person's own step asks of the person, where its work names it."""
    fallback_human: bool = False
    fallback_when: str | None = None
    fallback_role: str | None = None
    fallback_expertise: tuple[str, ...] = ()
    checks: tuple[CheckFacts, ...] = ()
    ask_role: str | None = None
    """The role a step's `ask` puts its act to (ADR-0088); None where it asks nothing."""

    @property
    def performer(self) -> str | None:
        return (self.role or OWNER) if self.method == "human" else None

    @property
    def taker(self) -> str | None:
        return (self.fallback_role or OWNER) if self.fallback_human else None


class ProcessFacts(Value):
    process: str = Field(min_length=1)
    version: str = Field(min_length=1)
    """The active version as `<process>@<version>`."""
    steps: tuple[StepFacts, ...] = ()


class StreamFacts(Value):
    stream: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    processes: tuple[str, ...] = ()


class AnchorFacts(Value):
    id: str = Field(min_length=1)
    class_: str = Field(min_length=1)
    act: str = Field(min_length=1)
    decider: str = Field(min_length=1)


class RequestFacts(Value):
    """A decision request not yet applied: its role and when it is due. No person."""

    decider: str = Field(min_length=1)
    due: date


class WaitFacts(Value):
    """A wait on a person that ended, at a step of a visible process, and the role it was
    addressed to."""

    process: str = Field(min_length=1)
    step: str = Field(min_length=1)
    role: str | None = None
    seconds: float = Field(ge=0)


class OpenWaitFacts(Value):
    process: str = Field(min_length=1)
    step: str = Field(min_length=1)
    role: str | None = None


class Ran(Value):
    """How often a step succeeded in the window, and by whom: Taktus, or a person."""

    process: str = Field(min_length=1)
    step: str = Field(min_length=1)
    automatic: int = Field(default=0, ge=0)
    """Performed by Taktus."""
    manual: int = Field(default=0, ge=0)
    """Performed by hand, under the step's role."""


class Facts(Value):
    processes: tuple[ProcessFacts, ...] = ()
    streams: tuple[StreamFacts, ...] = ()
    anchors: tuple[AnchorFacts, ...] = ()
    requests: tuple[RequestFacts, ...] = ()
    waits: tuple[WaitFacts, ...] = ()
    open_waits: tuple[OpenWaitFacts, ...] = ()
    ran: tuple[Ran, ...] = ()
    holders: Mapping[str, int] = Field(default_factory=dict)
    """How many identities hold each role. Never shown: it decides what is withheld."""
    units: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    own: Mapping[str, float] = Field(default_factory=dict)
    """Per role the reader holds, the seconds of the waits at it the reader ended."""
    days: int = Field(ge=1)


# --- the views ------------------------------------------------------------------------------


class StreamRef(Value):
    stream: str
    name: str


class Duty(Value):
    """A step the role performs, or takes over."""

    process: str
    step: str
    task: str
    expertise: tuple[str, ...] = ()
    when: str | None = None
    """For a step it takes over: when the step falls back to the role."""


class Decides(Value):
    kind: str
    """`anchor` — an act of the tenant's anchors; `ask` — a step's own question."""
    ref: str
    act: str


class Supervises(Value):
    process: str
    step: str
    check: str


class Figure(Value):
    """A figure, or the reason it is withheld. Never both."""

    value: float | None = None
    withheld: str | None = None


class Load(Value):
    open_waits: int = Field(ge=0)
    """The waits addressed to the role now: what the processes ask of it at this moment."""
    performed: Figure
    """How often a step of the role was performed in the window."""
    if_taktus_stopped_steps: int = Field(ge=0)
    """The steps Taktus performs whose fallback is the role."""
    if_taktus_stopped_runs: int = Field(ge=0)
    """How often Taktus performed them in the window: what would come to the role."""


class Waiting(Value):
    seconds: Figure
    """The time steps waited at the role in the window."""
    own_seconds: float | None = None
    """The reader's own waits at the role, where the reader holds it. Never anyone else's."""


class Requests(Value):
    open: int = Field(ge=0)
    oldest_due: date | None = None


class RoleProfile(Value):
    role: str
    days: int
    units: tuple[str, ...] = ()
    """The units of the structure the role sits in: where it is, never who holds it."""
    responsible_for: tuple[StreamRef, ...] = ()
    serves: tuple[StreamRef, ...] = ()
    performs: tuple[Duty, ...] = ()
    takes_over: tuple[Duty, ...] = ()
    decides: tuple[Decides, ...] = ()
    supervises: tuple[Supervises, ...] = ()
    expertise: tuple[str, ...] = ()
    load: Load
    waiting: Waiting
    requests: Requests
    workforce: str = WORKFORCE
    review: str = REVIEW
    text: str = Field(min_length=1)


class RoleSummary(Value):
    role: str
    performs: int
    takes_over: int
    decides: int
    supervises: int
    open_requests: int


class RoleIndex(Value):
    roles: tuple[RoleSummary, ...]
    review: str = REVIEW


# --- the derivation ---------------------------------------------------------------------------


def roles(facts: Facts) -> tuple[str, ...]:
    """Every role the structure holds or the processes, streams and anchors name, sorted."""
    named: set[str] = set(facts.holders)
    for process in facts.processes:
        for step in process.steps:
            named.update(r for r in (step.performer, step.taker, step.ask_role) if r)
            named.update(c.role for c in step.checks if c.kind in SUPERVISING and c.role)
    named.update(s.role for s in facts.streams)
    named.update(a.decider for a in facts.anchors)
    return tuple(sorted(named))


def index(facts: Facts) -> RoleIndex:
    found = []
    for role in roles(facts):
        p = profile(facts, role)
        found.append(
            RoleSummary(
                role=role,
                performs=len(p.performs),
                takes_over=len(p.takes_over),
                decides=len(p.decides),
                supervises=len(p.supervises),
                open_requests=p.requests.open,
            )
        )
    return RoleIndex(roles=tuple(found))


def profile(facts: Facts, role: str) -> RoleProfile:
    performs: list[Duty] = []
    takes_over: list[Duty] = []
    decides: list[Decides] = []
    supervises: list[Supervises] = []
    acted_in: set[str] = set()
    stopped: set[tuple[str, str]] = set()
    own_steps: set[tuple[str, str]] = set()
    for process in facts.processes:
        for step in process.steps:
            if step.performer == role:
                performs.append(
                    Duty(
                        process=process.process,
                        step=step.id,
                        task=step.task or step.reason,
                        expertise=step.expertise,
                    )
                )
                acted_in.add(process.process)
                own_steps.add((process.process, step.id))
            if step.taker == role:
                takes_over.append(
                    Duty(
                        process=process.process,
                        step=step.id,
                        task=step.reason,
                        expertise=step.fallback_expertise,
                        when=step.fallback_when,
                    )
                )
                acted_in.add(process.process)
                if step.method != "human":
                    stopped.add((process.process, step.id))
            if step.ask_role == role:
                decides.append(
                    Decides(kind="ask", ref=f"{process.process}/{step.id}", act=step.reason)
                )
            for check in step.checks:
                if check.kind in SUPERVISING and check.role == role:
                    supervises.append(
                        Supervises(process=process.process, step=step.id, check=check.kind)
                    )
                    acted_in.add(process.process)
    decides[:0] = [
        Decides(kind="anchor", ref=a.id, act=a.act)
        for a in sorted(facts.anchors, key=lambda a: a.id)
        if a.decider == role
    ]
    responsible = tuple(
        StreamRef(stream=s.stream, name=s.name)
        for s in sorted(facts.streams, key=lambda s: s.stream)
        if s.role == role
    )
    serves = tuple(
        StreamRef(stream=s.stream, name=s.name)
        for s in sorted(facts.streams, key=lambda s: s.stream)
        if acted_in & set(s.processes)
    )
    expertise = _distinct(e for duty in (*performs, *takes_over) for e in duty.expertise)

    few = facts.holders.get(role, 0) < TOO_FEW
    reason = withheld_reason(role)
    performed = sum(r.manual for r in facts.ran if (r.process, r.step) in own_steps)
    waited = sum(w.seconds for w in facts.waits if (w.role or OWNER) == role)
    load = Load(
        open_waits=sum(1 for w in facts.open_waits if (w.role or OWNER) == role),
        performed=Figure(withheld=reason) if few else Figure(value=performed),
        if_taktus_stopped_steps=len(stopped),
        if_taktus_stopped_runs=sum(
            r.automatic for r in facts.ran if (r.process, r.step) in stopped
        ),
    )
    waiting = Waiting(
        seconds=Figure(withheld=reason) if few else Figure(value=waited),
        own_seconds=facts.own.get(role),
    )
    open_requests = [r for r in facts.requests if r.decider == role]
    requests = Requests(
        open=len(open_requests),
        oldest_due=min((r.due for r in open_requests), default=None),
    )
    drafted = RoleProfile(
        role=role,
        days=facts.days,
        units=facts.units.get(role, ()),
        responsible_for=responsible,
        serves=serves,
        performs=tuple(performs),
        takes_over=tuple(takes_over),
        decides=tuple(decides),
        supervises=tuple(supervises),
        expertise=expertise,
        load=load,
        waiting=waiting,
        requests=requests,
        text="-",
    )
    return drafted.model_copy(update={"text": _text(drafted)})


def _distinct(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _figure(figure: Figure, unit: str) -> str:
    if figure.withheld is not None:
        return figure.withheld
    value = figure.value or 0
    return f"{value:g} {unit}"


def _text(p: RoleProfile) -> str:
    parts = [
        f"The role {p.role}: performs {len(p.performs)} step(s), takes over {len(p.takes_over)}, "
        f"decides {len(p.decides)}, supervises {len(p.supervises)}.",
        f"Now {p.load.open_waits} wait(s) at it; performed in {p.days} days: "
        f"{_figure(p.load.performed, 'time(s)')}; waited at it: "
        f"{_figure(p.waiting.seconds, 'seconds')}.",
        f"If Taktus stopped, {p.load.if_taktus_stopped_steps} step(s) would come to it, run "
        f"{p.load.if_taktus_stopped_runs} time(s) in {p.days} days.",
        f"{p.requests.open} decision request(s) open for it.",
        p.workforce,
        p.review,
    ]
    return " ".join(parts)


# --- the export -------------------------------------------------------------------------------


def description(p: RoleProfile) -> str:
    """The profile as a draft position description, in Markdown. No time figure, nothing of the
    reader's own, no person (ADR-0167 §5)."""
    lines = [
        f"# Draft position description: role `{p.role}`",
        "",
        f"> **Draft.** {p.review}",
        ">",
        f"> {p.workforce}",
        "",
    ]
    lines += _section(
        "Where the role sits", [f"`{u}`" if u else "the top of the structure" for u in p.units]
    )
    lines += _section(
        "Value streams",
        [f"responsible for {s.name} (`{s.stream}`)" for s in p.responsible_for]
        + [f"serves {s.name} (`{s.stream}`)" for s in p.serves],
    )
    lines += _section("Performs", [_duty(d) for d in p.performs])
    lines += _section("Must be able to take over", [_duty(d) for d in p.takes_over])
    lines += _section("Decides", [f"{d.act} ({d.kind} `{d.ref}`)" for d in p.decides])
    lines += _section(
        "Supervises", [f"the {s.check} check of `{s.process}/{s.step}`" for s in p.supervises]
    )
    lines += _section("Expertise needed", list(p.expertise))
    lines += _section(
        "If Taktus stopped",
        [f"{p.load.if_taktus_stopped_steps} step(s) Taktus performs now would come to the role."]
        if p.load.if_taktus_stopped_steps
        else [],
    )
    return "\n".join(lines).rstrip() + "\n"


def _duty(d: Duty) -> str:
    text = f"`{d.process}/{d.step}`: {d.task}"
    if d.when:
        text += f" (when {d.when})"
    if d.expertise:
        text += f"; needs {', '.join(d.expertise)}"
    return text


def _section(title: str, items: Sequence[str]) -> list[str]:
    body = [f"- {item}" for item in items] or ["- none"]
    return [f"## {title}", "", *body, ""]
