"""Each process's level and its correction rates, on the HTTP surface (ADR-0122, UC-7.5).

`GET /autonomy` answers, for every process the reader may see, four things. The level its
active version states, and why (ADR-0026). The level a rule lowered it to, and the incident that
says why (ADR-0110 §4). The level in force: the lower of the two. And the correction rate of the
process and of each of its action classes over 7 and 28 days, with the raise Taktus proposed on
them since the unit's last change of level (ADR-0110 §3, §8).

Read with an account key in `Authorization: Bearer`. A process the reader may not see is absent,
by the one predicate of the live representation (ADR-0055 §5). Every figure is counted per
process and action class. None names the person who released, corrected or rejected
(principle 14, ADR-0015): the ledger entries the rule reads carry no actor.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from taktus.adapters.driving.rest.problems import MEDIA_TYPE, problem
from taktus.adapters.driving.rest.wiring import RestServices
from taktus.components.governance.domain.model import (
    CorrectionLimits,
    Figures,
    Incident,
    Lowered,
    Proposed,
    Rate,
)
from taktus.components.reporting.domain.model import Reader
from taktus.components.reporting.domain.service.levels import ProcessElement
from taktus.ports.identity import Resolution

type Authenticated = Callable[[RestServices, str | None], Awaitable[Resolution | None]]

PROBLEM: dict[str, Any] = {"content": {MEDIA_TYPE: {}}}
NEEDS_KEY = "an account key is needed: Authorization: Bearer <key>"


def _percent(share: float) -> str:
    return f"{round(share * 100)} %"


def rate_document(rate: Rate) -> dict[str, Any]:
    """One window's counts, and the rate where anything was decided."""
    return {
        "days": rate.window.days,
        "since": rate.since.isoformat(),
        "decided": rate.decided,
        "released": rate.released,
        "corrected": rate.corrected,
        "rejected": rate.rejected,
        "rate": rate.rate,
    }


def _rate_text(rate: Rate) -> str:
    if rate.rate is None:
        return f"nothing decided over {rate.window.days} days"
    changed = rate.corrected + rate.rejected
    return (
        f"{changed} of {rate.decided} corrected or rejected over {rate.window.days} days "
        f"({_percent(rate.rate)})"
    )


def unit_document(figures: Figures, level: int) -> dict[str, Any]:
    """One unit — the process, or one action class of it — with its rates and its level."""
    unit = figures.unit
    named = "The process" if unit.action is None else f"The action {unit.action}"
    document: dict[str, Any] = {
        "action": unit.action,
        "level": level,
        "week": rate_document(figures.week),
        "month": rate_document(figures.month),
        "text": f"{named}: {_rate_text(figures.week)}; {_rate_text(figures.month)}.",
    }
    if figures.counted_since is not None:
        document["counted_since"] = figures.counted_since.isoformat()
    if figures.changed_at is not None:
        document["changed_at"] = figures.changed_at.isoformat()
    return document


def lowering_document(incident: Incident) -> dict[str, Any]:
    """Why a level fell: the rule, when, in which run, and the facts it read."""
    return {
        "incident": incident.id,
        "rule": incident.rule,
        "raised_at": incident.raised_at.isoformat(),
        "run": incident.run_id,
        "unit": incident.facts.get("unit"),
        "level_before": incident.facts.get("level_before"),
        "level_after": incident.facts.get("level_after"),
        "facts": dict(incident.facts),
    }


def process_document(
    process: ProcessElement,
    lowered: Lowered,
    figures: Sequence[Figures],
    proposed: Sequence[Proposed],
    lowerings: Sequence[Incident],
) -> dict[str, Any]:
    """One process's level: stated, lowered, in force, why, and its units' rates.

    `figures`, `proposed` and `lowerings` are the process's own. A raise proposed counts only
    while no change of level followed it: its figures' last change is the unit's last change."""
    stated = process.autonomy
    in_force = stated.level if lowered.level is None else min(stated.level, lowered.level)

    def level_of(action: str | None) -> int:
        own = in_force if action is None else min(stated.level_of(action), in_force)
        fell = lowered.of(action)
        return own if fell is None else min(own, fell)

    current = {f.unit.action: f.changed_at for f in figures}
    raises = [
        {
            "action": p.figures.unit.action,
            "version": p.process_version,
            "at": p.figures.at.isoformat(),
            "week": rate_document(p.figures.week),
            "month": rate_document(p.figures.month),
        }
        for p in proposed
        if current.get(p.figures.unit.action, p.figures.changed_at) == p.figures.changed_at
    ]
    sentence = f"Runs at autonomy level {in_force}"
    if in_force < stated.level:
        sentence += f", lowered by rule from the stated {stated.level}"
    sentence += f": {stated.reason}."
    return {
        "id": process.id,
        "name": process.name,
        "version": process.version,
        "stated": stated.document(),
        "stated_text": process.autonomy_text,
        "lowered": lowered.document(),
        "in_force": in_force,
        "text": sentence,
        "lowerings": [lowering_document(i) for i in lowerings],
        "units": [unit_document(f, level_of(f.unit.action)) for f in figures],
        "raises_proposed": raises,
    }


def limits_document(limits: CorrectionLimits) -> dict[str, Any]:
    return {
        "raise_decisions": limits.raise_decisions,
        "raise_weeks": limits.raise_weeks,
        "raise_rate": limits.raise_rate,
        "lower_rate": limits.lower_rate,
        "lower_window_days": limits.lower_window.days,
        "lower_minimum": limits.lower_minimum,
        "shipped_default": limits.configured_at is None,
    }


def summary(processes: Sequence[dict[str, Any]]) -> str:
    """One sentence: how many processes, how many run below their stated level, how many
    raises wait for a person."""
    n = len(processes)
    if n == 0:
        return "No process you may see."
    below = sum(1 for p in processes if p["in_force"] < p["stated"]["level"])
    raises = sum(len(p["raises_proposed"]) for p in processes)
    parts = [f"{n} {'process' if n == 1 else 'processes'}"]
    parts.append(
        "none runs below its stated level"
        if below == 0
        else f"{below} of them {'runs' if below == 1 else 'run'} below the stated level by rule"
    )
    if raises:
        parts.append(f"{raises} {'raise waits' if raises == 1 else 'raises wait'} for a person")
    return "; ".join(parts) + "."


def autonomy_document(
    processes: Sequence[dict[str, Any]], limits: CorrectionLimits
) -> dict[str, Any]:
    """The answer of `GET /autonomy`: the sentence first, then every process, then the limits."""
    return {
        "summary": summary(processes),
        "processes": list(processes),
        "limits": limits_document(limits),
    }


def router(services: RestServices, authenticated: Authenticated) -> APIRouter:
    routes = APIRouter(tags=["autonomy"])

    @routes.get(
        "/autonomy",
        summary="Each process's level, why it is there, and its correction rates",
        description="For every process you may see: the level its active version states and "
        "why (ADR-0026), the level a rule lowered it to and the incident that says why, the "
        "level in force, and the correction rate of the process and of each of its action "
        "classes over 7 and 28 days, with any raise Taktus proposed since the unit's last "
        "change of level (ADR-0110). With the tenant's limits. Counted per process and action "
        "class: no figure names a person (principle 14, ADR-0015).",
        responses={
            200: {"description": "The levels and their rates."},
            401: {"description": "No account key, or one that proves no identity.", **PROBLEM},
            422: {"description": "A parameter does not validate.", **PROBLEM},
        },
    )
    async def autonomy(authorization: str | None = Header(default=None)) -> JSONResponse:
        who = await authenticated(services, authorization)
        if who is None:
            return problem(401, NEEDS_KEY)
        reader = Reader(tenant=who.tenant, identity=who.identity, roles=who.roles)
        corrections = services.corrections
        overview = await services.levels.overview(reader)
        figures = await corrections.figures(who.tenant)
        proposed = await corrections.proposed(who.tenant)
        lowerings = await corrections.lowerings(who.tenant)
        processes: list[dict[str, Any]] = []
        for area in overview.areas:
            for summary_ in area.processes:
                level = await services.levels.process(reader, summary_.id)
                if level is None:
                    continue
                process = level.process
                version = f"{process.id}@{process.version}"
                processes.append(
                    process_document(
                        process,
                        await corrections.lowered(who.tenant, version),
                        [f for f in figures if f.unit.process_id == process.id],
                        [p for p in proposed if p.process_version == version],
                        [i for i in lowerings if i.process_version == version],
                    )
                )
        limits = await corrections.limits(who.tenant)
        return JSONResponse(autonomy_document(processes, limits))

    return routes
