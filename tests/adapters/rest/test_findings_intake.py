"""The intake of other instances' findings on the HTTP surface (ADR-0118).

What the intake decides is held by `tests/composition/test_findings_intake.py`, over this same
route. Here: the route exists under every prefix, admits no credential, and is closed unless
the operator opened it.
"""

from __future__ import annotations

import httpx

from .conftest import Services


async def test_the_intake_is_closed_unless_its_operator_opened_it(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, _, base = client
    answered = await http.post(
        f"{base}/findings/intake", json={"key": "k", "payload": "{}", "signature": "s"}
    )
    assert answered.status_code == 404
    assert "TAKTUS_FINDINGS_INTAKE_TENANT" in answered.json()["detail"]


async def test_a_field_the_intake_does_not_know_is_refused(
    client: tuple[httpx.AsyncClient, Services, str],
) -> None:
    http, _, base = client
    answered = await http.post(
        f"{base}/findings/intake",
        json={"key": "k", "payload": "{}", "signature": "s", "token": "a bearer"},
    )
    assert answered.status_code == 422, "no credential is admitted beside the signature"
