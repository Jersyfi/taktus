"""A deprecated operation of the HTTP surface names its removal and says so in every answer
(ADR-0220 §3, §4).

The committed `api/openapi.yaml` holds every deprecation to its form: a removal `N.0.0` and the
date. A route deprecated with `deprecated(...)` answers with `Deprecation` (RFC 9745) and
`Taktus-Removal`; one that is not answers with neither. A removal that is not a major is refused
where the route is written.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi import FastAPI

from taktus.adapters.driving.rest.deprecation import Deprecations, deprecated

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

import validate_contracts  # noqa: E402 — a script under tools/, found through the line above


def test_every_deprecation_of_the_http_surface_names_its_removal_and_date() -> None:
    document = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))
    assert validate_contracts.deprecations(document) == []


async def test_a_deprecated_route_says_so_in_its_answer_and_another_does_not() -> None:
    app = FastAPI()
    app.add_middleware(Deprecations)

    @app.get("/old", **deprecated(since="2026-11-07", removal="2.0.0"))
    async def old() -> dict[str, str]:
        return {"still": "served"}

    @app.get("/kept")
    async def kept() -> dict[str, str]:
        return {"kept": "yes"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://taktus.test"
    ) as http:
        answer = await http.get("/old")
        other = await http.get("/kept")
    assert answer.status_code == 200 and answer.json() == {"still": "served"}
    since = int(datetime(2026, 11, 7, tzinfo=UTC).timestamp())
    assert answer.headers["Deprecation"] == f"@{since}"
    assert answer.headers["Taktus-Removal"] == "2.0.0"
    assert "Deprecation" not in other.headers and "Taktus-Removal" not in other.headers
    operation = app.openapi()["paths"]["/old"]["get"]
    assert operation["deprecated"] is True
    assert validate_contracts.deprecations({"paths": {"/old": {"get": operation}}}) == []


@pytest.mark.parametrize(
    ("since", "removal"), [("2026-11-07", "2.1.0"), ("7.11.2026", "2.0.0"), ("2026-13-01", "2.0.0")]
)
def test_a_removal_that_is_not_a_major_or_a_date_that_is_none_is_refused(
    since: str, removal: str
) -> None:
    with pytest.raises(ValueError):
        deprecated(since=since, removal=removal)
