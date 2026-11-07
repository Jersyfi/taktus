#!/usr/bin/env python3
"""The `browser` worker: web pages checked in headless Chromium, behind the worker contract v1.

A step of a process that has to look at a web application the way a person does — open a page,
click through a flow, read what it shows — names the capability `browser.check` and hands this
worker its checks (`task.inputs.checks`). Each check is one step of the assignment: the worker
runs `browse.py`, which drives headless Chromium through Playwright, and the step's artifact is
the check's report. A last step, `report`, gathers every check's report into the artifact
`report`, with how many passed and which failed, so that a process reads one artifact. A check
that does not hold is a finding in the report, not a failure.

Everything the contract asks for around the steps — capabilities, the estimate, the resumable
event stream, consumption and a boundary with a checkpoint after every step, a stop at a
boundary, a tool or a host outside the frame refused, the limits held, steering, handover and
the outbound binding — is the reference worker's (`workers/script/worker.py`). This worker
loads that file and gives it other steps: it declares `browser.check` as its tool, plans one
step per check, estimates per check, and names every host a check reaches, so that each is held
against `allowed_hosts` before the browser starts; inside the browser every other host is
refused (`browse.py`). One file of the contract, kept once.

Credentials arrive as names. A check's `fill` may name one by `value_env`; the browser types its
value and nothing writes it anywhere.

It imports nothing from src/taktus. It is a separate deployable, as every worker is:
`python3 workers/browser/worker.py --port 9000`.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import shlex
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
BROWSE = HERE / "browse.py"
VERSION = "1.0.0"  # this worker's own version, recorded in the provenance of what it produces
TOOL = "browser.check"
REPORT = "report"
CAPABILITIES = [TOOL, "browser.headless", "workspace.isolated"]
CHECK_SECONDS = float(os.environ.get("TAKTUS_BROWSER_CHECK_SECONDS") or 8.0)
"""The compute seconds one check is planned at: a browser's start, a page and its steps."""


def _reference() -> ModuleType:
    """The reference worker, from beside this file in the image, or from the repository."""
    for candidate in (HERE / "script_worker.py", HERE.parent / "script" / "worker.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("script_worker", candidate)
            if spec is None or spec.loader is None:
                break
            module = importlib.util.module_from_spec(spec)
            sys.modules["script_worker"] = module
            spec.loader.exec_module(module)
            return module
    raise SystemExit("the reference worker's file is missing beside the browser worker")


script = _reference()
Json = dict[str, Any]


def checks_of(task: Json) -> list[Json]:
    checks = task.get("inputs", {}).get("checks")
    if isinstance(checks, list) and checks and all(isinstance(c, dict) for c in checks):
        return [c for c in checks if isinstance(c.get("url"), str) and c["url"]]
    return []


def hosts_of(task: Json) -> list[str]:
    """Every host the task reaches: those it declares, and each check's own."""
    declared = task.get("inputs", {}).get("hosts")
    hosts = list(declared) if isinstance(declared, list) else []
    hosts += [urlparse(c["url"]).hostname or "" for c in checks_of(task)]
    return [h for h in dict.fromkeys(str(h) for h in hosts) if h]


_script_work_for = script.work_for


def work_for(task: Json, profile: str, options: Any) -> list[Any]:
    """One step per check, each running `browse.py` on it; a task without checks does the
    profile's work, as the reference worker does."""
    checks = checks_of(task)
    if not checks:
        return _script_work_for(task, profile, options)
    hosts = hosts_of(task)
    steps = []
    for n, check in enumerate(checks, 1):
        given = {**check, "hosts": hosts}
        command = " ".join(
            shlex.quote(part) for part in (sys.executable, str(BROWSE), json.dumps(given))
        )
        steps.append(
            script.PlannedStep(
                f"check-{n}",
                "browser",
                f"check {check.get('name') or check['url']}"[:80],
                command,
                CHECK_SECONDS,
                (script.ArtifactSpec(f"check-{n}", "report", "application/json"),),
            )
        )
    steps.append(
        script.PlannedStep(
            REPORT,
            "browser",
            "gather the reports of every check",
            "true",
            0.0,
            (script.ArtifactSpec(REPORT, "report", "application/json"),),
        )
    )
    return steps


def gathered(reports: list[bytes]) -> bytes:
    """Every check's report, how many passed, and the name of each that did not."""
    checks = []
    for content in reports:
        try:
            checks.append(json.loads(content))
        except ValueError:
            checks.append({"passed": False, "error": "the check wrote no report"})
    failed = [str(c.get("name") or c.get("url")) for c in checks if not c.get("passed")]
    document = {
        "checks": checks,
        "count": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failures": failed,
    }
    return json.dumps(document, sort_keys=True).encode("utf-8")


class BrowserWorker(script.Worker):  # type: ignore[misc, name-defined]
    def _produce(self, assignment: Any, step: Any, output: bytes, credential: Any) -> None:
        """The last step's artifact is gathered from the checks' own, those an assignment
        resumed after included; every other step's is its command's output."""
        if step.step_id != REPORT or step.kind != "browser":
            super()._produce(assignment, step, output, credential)
            return
        with assignment.lock:
            held = [*assignment.inherited, *assignment.produced]
        reports = [
            p.content for p in held if p.artifact_id.startswith("check-") and p.kind == "report"
        ]
        content = gathered(reports)
        super()._produce(
            assignment,
            script.PlannedStep(
                step.step_id,
                step.kind,
                step.summary,
                step.command,
                step.seconds,
                (script.ArtifactSpec(REPORT, "report", "application/json", content),),
            ),
            output,
            credential,
        )

    def estimator(self) -> Json:
        """A step per check the task carries, else the profile's plan; never less than what
        `estimate` answers for a fresh assignment (W-02)."""
        each = math.ceil(float(self.options.estimate_factor) * CHECK_SECONDS * 1000)
        if self.fault == "W-02-estimator":
            each = each // 10
        found = super().estimator()
        seconds = each / 1000
        found["input"] = "checks"
        found["each"] = {
            "confidence": "low",
            "compute_seconds": seconds,
            "resource_class": self.resource_class,
            "wall_seconds": int(seconds) + 1,
            # The check's step, and a share of the last step that gathers them: never fewer
            # steps than the plan holds (W-02).
            "steps": 2,
        }
        return found


script.VERSION = VERSION
script.TOOL = TOOL
script.CAPABILITIES = CAPABILITIES
script.work_for = work_for
script.hosts_of = hosts_of
script.Worker = BrowserWorker


if __name__ == "__main__":
    sys.exit(script.main())
