"""`api/openapi.yaml` is generated, never edited by hand: it equals what `make generate`
writes, is OpenAPI 3.1, and names the path prefix as a server variable."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
GENERATE = ROOT / "tools" / "generate.py"
OPENAPI = ROOT / "api" / "openapi.yaml"


def generated() -> str:
    specification = importlib.util.spec_from_file_location("generate", GENERATE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules["generate"] = module
    specification.loader.exec_module(module)
    document: str = module.openapi_document()
    return document


def test_the_committed_document_is_what_make_generate_writes() -> None:
    assert OPENAPI.is_file(), "run `make generate`"
    assert OPENAPI.read_text(encoding="utf-8") == generated(), (
        "api/openapi.yaml is out of date: run `make generate` and commit the result"
    )


def test_the_document_is_openapi_3_1_with_the_prefix_as_a_server_variable() -> None:
    document = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.1")
    assert document["servers"] == [
        {
            "url": "{prefix}",
            "description": "The path prefix the instance is served under (TAKTUS_PATH_PREFIX).",
            "variables": {"prefix": {"default": "/"}},
        }
    ]
    assert set(document["paths"]) == {
        "/health",
        "/ready",
        "/intake/{channel}",
        "/intake-events/{event_id}/complete",
        "/identity/link-codes",
        "/identity/agent-key",
        "/register",
        "/register/inventory",
        "/register/{adapter}/stop",
        "/dependencies/remove/{adapter}",
        "/dependencies/wrong-result/{run_id}/{step_id}",
        "/dependencies/residency",
        "/processes/{process_id}/variants",
        "/session",
        "/decisions",
        "/decisions/response-times",
        "/decisions/{request_id}",
        "/decisions/{request_id}/answer",
        "/decisions/{request_id}/confirm",
        "/findings/intake",
        "/findings",
        "/findings/{lack}/review",
        "/findings/{lack}/review/confirm",
        "/autonomy",
        "/owner/reports",
        "/owner/reports/{report_id}",
        "/owner/reports/{report_id}/text",
        "/owner/reports/{report_id}/answer",
        "/owner/reports/{report_id}/confirm",
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/ledger",
        "/runs/{run_id}/spend",
        "/processes/{process_id}/spend",
        "/trials",
        "/trials/offers",
        "/trials/{trial_id}",
        "/runs/{run_id}/steps/{step_id}/messages",
        "/runs/{run_id}/steps/{step_id}/takeover",
        "/runs/{run_id}/takeovers/{takeover_id}",
        "/runs/{run_id}/takeovers/{takeover_id}/hand-back",
        "/changes",
        "/levels/runs/{run_id}",
        "/levels/runs/{run_id}/stages",
        "/catalogue",
        "/catalogue/{process_id}/start",
        "/streams",
        "/streams/{stream}",
        "/roles",
        "/roles/{role}",
        "/roles/{role}/description",
        "/levels/processes/{process_id}",
        "/levels/overview",
        "/levels/origins/{run_id}/{step_id}",
        "/levels/runs/{run_id}/steps/{step_id}/trace",
        "/levels/runs/{run_id}/steps/{step_id}/trace/shares",
        "/levels/runs/{run_id}/steps/{step_id}/trace/shares/{role}",
        "/vocabulary",
        "/operation",
        "/incidents",
        "/alerts",
        "/backup",
        "/signals",
        "/signals/daily-report",
        "/processes/{process_id}/proposals",
        "/processes/{process_id}/proposals/{proposal_id}",
        "/processes/{process_id}/proposals/{proposal_id}/discard",
        "/processes/{process_id}/proposals/{proposal_id}/rehearse",
        "/processes/{process_id}/proposals/{proposal_id}/commission",
        "/gallery",
        "/gallery/{blueprint_id}/{process_id}/proposals",
        "/processes/{process_id}/rollback",
        "/processes/{process_id}/evaluations",
        "/processes/{process_id}/evaluations/{evaluation_id}",
        "/processes/{process_id}/evaluation-cases",
        "/processes/{process_id}/evaluation-cases/{case_id}/confirm",
        "/processes/{process_id}/evaluation-cases/{case_id}/reject",
        "/administration/tenants",
        "/administration/tenants/{tenant}",
        "/workers/{name}/relay/next",
        "/workers/{name}/relay/answers/{request_id}",
    }
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if int(status) >= 400:
                    assert "application/problem+json" in response.get("content", {}), (
                        f"{method.upper()} {path} {status} is not a problem"
                    )
