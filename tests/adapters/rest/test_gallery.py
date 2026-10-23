"""The gallery on the HTTP surface (UC-10.4, ADR-0136 §5, issue #405).

`GET /gallery` lists the blueprints with their processes, steps and choices; choosing one makes
a proposal against no version, with the choices; a blueprint the gallery does not hold is
`404`, a choice it does not offer `400` with the finding; a key is needed for both.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from taktus.adapters.driven.memory import MemoryRepository
from taktus.components.process.domain.model import ProcessVersion
from taktus.composition.gallery import Gallery

from .conftest import Services

type Client = tuple[httpx.AsyncClient, Services, str]

GALLERY = Path(__file__).resolve().parents[3] / "blueprints" / "gallery"


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def with_gallery(given: Services) -> None:
    given.chosen = Gallery(
        GALLERY,
        given.proposals,
        MemoryRepository(given.persistence, ProcessVersion),
        given.persistence,
    )


async def test_the_gallery_is_listed_and_a_choice_becomes_a_proposal(client: Client) -> None:
    http, given, base = client
    with_gallery(given)
    key = await given.linked()
    listed = await http.get(f"{base}/gallery", headers=bearer(key))
    assert listed.status_code == 200, listed.text
    blueprints = listed.json()["blueprints"]
    assert len(blueprints) == 3
    first = blueprints[0]
    process = first["processes"][0]
    assert process["level"] <= 2 and process["steps"] and process["choices"]
    choice = process["choices"][0]
    made = await http.post(
        f"{base}/gallery/{first['id']}/{process['id']}/proposals",
        json={"choices": {choice["name"]: "chosen by the person"}},
        headers=bearer(key),
    )
    assert made.status_code == 201, made.text
    proposal = made.json()
    assert "base_version" not in proposal and proposal["state"] == "proposed"
    (trigger,) = proposal["bundle"]["triggers"]
    assert trigger["inputs"][choice["name"]] == "chosen by the person"
    again = await http.get(f"{base}/processes/{process['id']}/proposals", headers=bearer(key))
    assert [p["id"] for p in again.json()["proposals"]] == [proposal["id"]]


async def test_what_the_gallery_does_not_hold_or_offer_is_refused_and_a_key_is_needed(
    client: Client,
) -> None:
    http, given, base = client
    with_gallery(given)
    key = await given.linked()
    first = (await http.get(f"{base}/gallery", headers=bearer(key))).json()["blueprints"][0]
    process = first["processes"][0]["id"]
    unknown = await http.post(
        f"{base}/gallery/nowhere/{process}/proposals", json={}, headers=bearer(key)
    )
    assert unknown.status_code == 404
    refused = await http.post(
        f"{base}/gallery/{first['id']}/{process}/proposals",
        json={"choices": {"autonomy": 4}},
        headers=bearer(key),
    )
    assert refused.status_code == 400
    assert "no choice 'autonomy'" in refused.json()["findings"][0]
    assert (await http.get(f"{base}/gallery")).status_code == 401
    missing = await http.post(f"{base}/gallery/{first['id']}/{process}/proposals", json={})
    assert missing.status_code == 401
