"""`make generate`: regenerate what is generated. Runs in the project environment.

Two things are generated today, each never edited by hand:

- `api/openapi.yaml`, the OpenAPI 3.1 document of Taktus' own REST interface, from the FastAPI
  application under `src/taktus/adapters/driving/rest` — built at the root; the path prefix an
  instance is served under is a server variable of the document.
  `tests/adapters/rest/test_openapi.py` fails when the file differs from what this script writes.
- `web/src/lib/generated/fixtures.json`, what the web app's tests draw: the visual vocabulary
  and a run level drawn by `reporting` from example facts that use every method kind, every
  exactness class and every motion, the process level of the same steps, and an overview (ADR-0063,
  ADR-0064, ADR-0067). The web app's tests hold what it draws to these glyphs;
  `tests/components/reporting/test_run_level.py` fails when the file differs from what this
  script writes. The web app itself reads the vocabulary and every level from the surface.

The shared kernel's Python types under src/taktus/shared/ are a hand-written binding checked
against the schemas by tests/contract, not generated (docs/architecture/project-structure.md
§4 says why).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "api" / "openapi.yaml"
FIXTURES = ROOT / "web" / "src" / "lib" / "generated" / "fixtures.json"


def openapi_document() -> str:
    from taktus.adapters.driving.rest import build_app

    # The document depends on the routes alone; no service is called to produce it.
    app = build_app(_NoServices(), prefix="/")  # type: ignore[arg-type]
    return yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True, width=100)


def web_fixtures() -> str:
    from datetime import UTC, datetime

    from taktus.components.reporting.domain.model import (
        OverviewFacts,
        ProcessFacts,
        ProcessStepFacts,
        ProcessSummary,
        RunActivity,
        RunAtVersion,
        RunFacts,
        RunningStep,
        StepFacts,
        VersionRef,
        Wait,
    )
    from taktus.components.reporting.domain.model.vocabulary import VOCABULARY
    from taktus.components.reporting.domain.service.levels import (
        overview_level,
        process_level,
        run_level,
    )
    from taktus.shared.v1 import Autonomy, ConsumptionQuantities

    at = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)

    def step(
        name: str, method: str, exactness: str | None, state: str, **more: object
    ) -> StepFacts:
        return StepFacts.model_validate(
            {"id": name, "method": method, "exactness": exactness, "state": state, **more}
        )

    facts = RunFacts(
        id="run_example",
        tenant="default",
        process_version="example@1",
        state="running",
        consumed=ConsumptionQuantities.model_validate(
            {"tokens_in": 1200, "tokens_out": 300, "currency": {"eur": 0.04}}
        ),
        steps=(
            step("load", "rule", "exact", "succeeded"),
            step("score", "statistics", "sourced", "running", depends_on=["load"]),
            step("classify", "ml", "tolerant", "failed", depends_on=["load"]),
            step("embed", "neural", "free", "stopped", depends_on=["load"]),
            step(
                "draft",
                "llm",
                "free",
                "running",
                depends_on=["score"],
                consumption={"tokens_in": 1200, "tokens_out": 300},
            ),
            step("build", "worker", "tolerant", "rejected", depends_on=["draft"]),
            step("review", "human", None, "running", depends_on=["draft"]),
            step(
                "pipeline",
                "wait",
                None,
                "waiting_human",
                depends_on=["review"],
                wait=Wait(
                    account="wait.human",
                    cause="awaiting_decision",
                    since=at,
                    role="finance.lead",
                    requests=("dr_example",),
                ),
            ),
            step("check", "rule", "exact", "admitted", depends_on=["pipeline"]),
            step("close", "rule", "exact", "planned", depends_on=["check"]),
        ),
        created_at=at,
        updated_at=at,
    )
    process = ProcessFacts(
        id="example",
        tenant="default",
        name="Example",
        version="1",
        autonomy=Autonomy.model_validate(
            {
                "level": 2,
                "reason": "a person confirms each step",
                "toward_next": "twenty runs without a result defect",
            }
        ),
        steps=tuple(
            ProcessStepFacts(
                id=s.id,
                method=s.method,
                exactness=s.exactness,
                reason=f"the {s.method} suits {s.id}",
                depends_on=s.depends_on,
            )
            for s in facts.steps
        ),
        versions=(VersionRef(version="1", active=True),),
        runs=(
            RunAtVersion(
                id="run_example",
                tenant="default",
                state="running",
                running=("score", "draft", "review"),
                created_at=at,
            ),
        ),
    )
    overview = OverviewFacts(
        tenant="default",
        processes=(
            ProcessSummary(id="example", name="Example", active_version="1", autonomy_level=2),
            ProcessSummary(id="quiet", name="Quiet", active_version="3", autonomy_level=4),
        ),
        runs=(
            RunActivity(
                id="run_example",
                tenant="default",
                process_version="example@1",
                state="running",
                working=True,
                waiting=False,
                running=tuple(
                    RunningStep(id=s.id, method=s.method, exactness=s.exactness)
                    for s in facts.steps
                    if s.state == "running"
                ),
            ),
            RunActivity(
                id="run_waiting",
                tenant="default",
                process_version="example@1",
                state="waiting_human",
                working=False,
                waiting=True,
            ),
        ),
    )
    document = {
        "vocabulary": VOCABULARY.document(),
        "overview": overview_level(overview).document(),
        "run_level": run_level(facts).document(),
        "process_level": process_level(process).document(),
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


class _NoServices:
    """Stands in for `RestServices` while the document is produced; nothing is called."""

    roles: tuple[str, ...] = ()
    tenants: tuple[str, ...] = ("default",)
    leading = False


def main() -> int:
    document = openapi_document()
    OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    changed = not OPENAPI.is_file() or OPENAPI.read_text(encoding="utf-8") != document
    OPENAPI.write_text(document, encoding="utf-8")
    print(f"generate: {OPENAPI.relative_to(ROOT)} {'written' if changed else 'unchanged'}")
    fixtures = web_fixtures()
    FIXTURES.parent.mkdir(parents=True, exist_ok=True)
    changed = not FIXTURES.is_file() or FIXTURES.read_text(encoding="utf-8") != fixtures
    FIXTURES.write_text(fixtures, encoding="utf-8")
    print(f"generate: {FIXTURES.relative_to(ROOT)} {'written' if changed else 'unchanged'}")
    print("  shared kernel: a checked binding under src/taktus/shared/ (tests/contract)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
