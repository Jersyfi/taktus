"""The run level, the vocabulary and the web app on the HTTP surface (ADR-0063, issue #105).

The run level answers only a reader whose key proves an identity, and a run the reader may not
see exactly as one that does not exist. Its figures are the run's own, as the read API gives the
run. The vocabulary is served as the one document. The web app's build is served under the
prefix, and its bare path is redirected relatively.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from taktus.adapters.driving.rest import build_app
from taktus.components.reporting.domain.model.vocabulary import VOCABULARY
from taktus.components.reporting.domain.service.drawing import Glyph, Run, Step, check
from taktus.components.run.domain.model import Run as RunRecord
from taktus.shared.v1 import ConsumptionQuantities

from .conftest import TENANT, Services, a_run, services

type Client = tuple[httpx.AsyncClient, Services, str]


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_the_run_level_needs_a_key(client: Client) -> None:
    http, given, base = client
    await a_run(given)
    assert (await http.get(f"{base}/levels/runs/run_1")).status_code == 401
    wrong = await http.get(f"{base}/levels/runs/run_1", headers=bearer("tk_nothing"))
    assert wrong.status_code == 401
    in_url = await http.get(f"{base}/levels/runs/run_1", params={"key": "tk_nothing"})
    assert in_url.status_code == 401


async def test_a_run_the_reader_may_not_see_is_answered_as_one_that_does_not_exist(
    client: Client,
) -> None:
    http, given, base = client
    run = await a_run(given)
    elsewhere = run.model_copy(update={"id": "run_2", "tenant": "other"})
    async with given.persistence.transaction("other"):
        await given.runs.put("other", elsewhere)
    _, key = await given.identity.person(TENANT, "idn_ada")
    unseen = await http.get(f"{base}/levels/runs/run_2", headers=bearer(key))
    missing = await http.get(f"{base}/levels/runs/run_9", headers=bearer(key))
    assert unseen.status_code == missing.status_code == 404
    assert unseen.json()["detail"] == "no run 'run_2' you may see"
    assert missing.json()["detail"] == "no run 'run_9' you may see"


async def test_the_run_level_draws_every_step_with_the_vocabularys_glyphs(client: Client) -> None:
    http, given, base = client
    run = await a_run(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    answer = await http.get(f"{base}/levels/runs/run_1", headers=bearer(key))
    assert answer.status_code == 200
    level = answer.json()
    assert level["run"]["id"] == "run_1" and level["run"]["state"] == "planned"
    assert [s["id"] for s in level["steps"]] == [s.id for s in run.steps]
    for motion, key_ in ((True, "moving"), (False, "still")):
        drawn: list[tuple[Step | Run, Glyph]] = [
            (
                Run(name=level["run"]["id"], state=level["run"]["state"]),
                Glyph.model_validate(level["run"]["drawn"][key_]),
            )
        ]
        drawn.extend(
            (
                Step(
                    name=s["id"],
                    method=s["method"],
                    exactness=s.get("exactness"),
                    state=s["state"],
                ),
                Glyph.model_validate(s["drawn"][key_]),
            )
            for s in level["steps"]
        )
        assert check(drawn, motion=motion) == ()


async def test_the_figures_are_the_runs_own_as_the_read_api_gives_the_run(client: Client) -> None:
    http, given, base = client
    await a_run(given)
    _, key = await given.identity.person(TENANT, "idn_ada")
    level = (await http.get(f"{base}/levels/runs/run_1", headers=bearer(key))).json()
    record = RunRecord.model_validate((await http.get(f"{base}/runs/run_1")).json())
    shown = {f["name"]: f["value"] for f in level["run"].get("consumed", [])}
    expected = record.consumed()
    assert shown == _flat(expected)


def _flat(quantities: ConsumptionQuantities) -> dict[str, float | int]:
    flat: dict[str, float | int] = {}
    for name, value in quantities.quantities().items():
        if name == "currency":
            flat.update({f"currency.{c}": v for c, v in value.items()})
        elif name == "tokens_by_model":
            for model, kinds in value.items():
                flat.update(
                    {f"tokens_by_model.{model}.{k}": n for k, n in kinds.document().items()}
                )
        elif name == "compute_seconds":
            flat[f"compute_seconds.{quantities.resource_class}"] = value
        else:
            flat[name] = value
    return flat


async def test_the_vocabulary_is_the_one_document(client: Client) -> None:
    http, _, base = client
    answer = await http.get(f"{base}/vocabulary")
    assert answer.status_code == 200
    assert answer.json() == VOCABULARY.document()


async def test_the_web_app_is_served_under_the_prefix_where_it_was_built(
    prefix: str, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>Taktus</title>", "utf-8")
    app = build_app(services(), prefix=prefix, web=tmp_path)
    base = "" if prefix == "/" else prefix
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://taktus.test"
    ) as http:
        page = await http.get(f"{base}/app/")
        assert page.status_code == 200 and "<title>Taktus</title>" in page.text
        bare = await http.get(f"{base}/app")
        assert bare.status_code == 308 and bare.headers["location"] == "app/"


async def test_without_a_build_no_web_app_is_served(prefix: str, tmp_path: Path) -> None:
    app = build_app(services(), prefix=prefix, web=tmp_path)
    base = "" if prefix == "/" else prefix
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://taktus.test"
    ) as http:
        assert (await http.get(f"{base}/app/")).status_code == 404
