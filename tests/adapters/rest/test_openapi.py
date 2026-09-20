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
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/ledger",
    }
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if int(status) >= 400:
                    assert "application/problem+json" in response.get("content", {}), (
                        f"{method.upper()} {path} {status} is not a problem"
                    )
