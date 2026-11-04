"""Takeover instructions for a test's own bundle (UC-6.3, ADR-0180).

Registration refuses a bundle without them. A test about something else gives its bundle the
plainest instructions that register: one entry per step, naming every credential the step's
work names literally. The shipped bundles carry written ones; `tests/components/process/
test_takeover_instructions.py` holds them to UC-6.3.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def instructions(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """The `takeover` section for the bundle's steps."""
    steps: dict[str, Any] = {}
    for step in bundle.get("steps") or ():
        steps[step["id"]] = {
            "system": "the system the step names",
            "do": f"do by hand what the step {step['id']} does",
            "expertise": "the step's own",
            "credentials": [
                {"parameter": name, "where": "the operator's secret store"}
                for name in sorted(set(_names(step.get("work"))))
            ],
            "done": "its result is written down",
        }
    return {"sequence": "the steps in the order the bundle gives them", "steps": steps}


def instructed(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """The bundle with its `takeover` section; one that has its own keeps it."""
    if "takeover" in bundle:
        return dict(bundle)
    return {**bundle, "takeover": instructions(bundle)}


def _names(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "credentials" and isinstance(value, list):
                found.extend(
                    item["name"]
                    for item in value
                    if isinstance(item, Mapping) and isinstance(item.get("name"), str)
                )
            else:
                found.extend(_names(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_names(item))
    return found
