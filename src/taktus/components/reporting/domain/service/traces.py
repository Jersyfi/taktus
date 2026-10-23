"""A line of a step's trace as a sentence, and the link a share hands on (ADR-0135 §3).

The sentence is made from what the worker contract carries for the event and nothing else.
A tool's arguments are a digest and are not shown; an artifact is named by kind, identifier
and the head of its digest.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from taktus.ports.traces import TraceLine

WEB_RUNS = "app/#/runs/"
"""Where the web app draws a run: its route is the part after `#` (ADR-0063)."""


def link(run_id: str, step_id: str) -> str:
    """The web app's page of the run, opened at the step's trace, relative to the surface."""
    return f"{WEB_RUNS}{quote(run_id, safe='')}/steps/{quote(step_id, safe='')}"


def text_of(line: TraceLine) -> str:
    d = line.detail
    match line.type:
        case "reach.stated":
            tools = ", ".join(_strings(d.get("tools")))
            hosts = ", ".join(_strings(d.get("hosts")))
            return f"Within reach: {tools or 'no tool'}" + (f"; hosts {hosts}" if hosts else "")
        case "step.started":
            summary = d.get("summary")
            return f"Started {d.get('kind', 'work')}" + (f": {summary}" if summary else "")
        case "step.progress":
            said = str(d.get("message", ""))
            measured = d.get("progress")
            if isinstance(measured, dict):
                current, total = measured.get("current"), measured.get("total")
                said += f" ({current} of {total} {measured.get('unit')})"
            return said or "Progress"
        case "tool.called":
            where = f" on {d['host']}" if d.get("host") else ""
            if d.get("refused"):
                reason = f": {d['reason']}" if d.get("reason") else ""
                return f"Refused {d.get('tool')}{where}{reason}"
            return f"Called {d.get('tool')}{where}"
        case "decision.made":
            chosen = f" {d['chosen']}" if d.get("chosen") else ""
            return f"Chose{chosen}: {d.get('rationale', '')}"
        case "consumption.reported":
            used = [
                f"{name} {value}"
                for name, value in sorted(d.items())
                if isinstance(value, int | float) and not isinstance(value, bool)
            ]
            for code, amount in sorted(_mapping(d.get("currency")).items()):
                used.append(f"{code} {amount}")
            return "Used " + (", ".join(used) or "nothing")
        case "step.boundary":
            return f"Reached a boundary: {d.get('checkpoint_ref')}"
        case "artifact.produced":
            digest = str(d.get("digest", ""))[:19]
            return f"Produced {d.get('kind')} {d.get('artifact_id')} ({digest}…)"
        case "assignment.finished":
            reason = f": {d['reason']}" if d.get("reason") else ""
            return f"Finished {d.get('outcome')}{reason}"
        case _:
            return line.type


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
