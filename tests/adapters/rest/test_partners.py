"""A mapping of a partner's messages proposed from sample data, on the HTTP surface (UC-15.3,
ADR-0315).

What is proven: a person who sends a contract and the partner's samples is answered with the
proposed mapping and the question it asks back; what could not be matched is asked, never
guessed; the draft is stored nowhere; a caller without a key is refused.
"""

from __future__ import annotations

import httpx

from .conftest import TENANT, Services
from .test_process_level import bearer
from .test_streams import stored
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

CONTRACT = {
    "partner": "a supplier",
    "direction": "import",
    "standard": "EN 16931",
    "fields": [{"name": "number"}, {"name": "currency"}, {"name": "seller"}],
    "frequency": "1d",
    "responsible": {"ours": "owner", "theirs": "the supplier"},
    "steps": ["read"],
}
SAMPLES = [
    {"invoice_no": "R-1", "Currency": "EUR", "seller": "S"},
    {"invoice_no": "R-2", "Currency": "EUR", "seller": "T"},
]


async def test_a_mapping_is_proposed_from_samples_and_asked_back(client: Client) -> None:
    http, given, base = client
    _, key = await given.identities.add(TENANT, "idn_ada", (TENANT,), roles=("accounting",))
    path = f"{base}/contracts/mapping-drafts"
    body = {"contract": CONTRACT, "samples": SAMPLES}
    assert is_problem(await http.post(path, json=body), 401)
    before = stored(given)
    answered = await http.post(path, json=body, headers=bearer(key))
    assert answered.status_code == 200, answered.text
    draft = answered.json()
    assert draft["proposed"] == {"currency": "Currency", "seller": "seller"}
    assert draft["unmatched"] == ["number"] and draft["unused"] == ["invoice_no"]
    assert "Is this right?" in draft["question"]
    assert stored(given) == before, "the draft is stored nowhere"
    wrong = await http.post(
        path, json={"contract": {**CONTRACT, "direction": "sideways"}, "samples": SAMPLES},
        headers=bearer(key),
    )  # fmt: skip
    assert is_problem(wrong, 422)
