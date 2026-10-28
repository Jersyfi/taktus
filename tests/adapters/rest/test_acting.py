"""What acts for a tenant, what depends on it, and how a process really runs, on the HTTP
surface (ADR-0147, UC-7.8, UC-6.15, UC-9.7).

Every route needs an account key; each hands the views the processes the reader may see, by the
live representation's predicate; a run or a process the reader may not see is answered as one
that does not exist; the stop is ADR-0138's, requested by the person. What the views gather is
held by `tests/composition/test_acting.py`."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from taktus.components.reporting.domain.model.acting import ActorFacts, Used
from taktus.components.reporting.domain.service import acting
from taktus.components.reporting.domain.service import variants as v
from taktus.components.run.application.service.stops import NotStoppable

from .conftest import TENANT, Services
from .test_process_level import bearer, bundle, register
from .test_surface import is_problem

type Client = tuple[httpx.AsyncClient, Services, str]

AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


class Views:
    """The views as the composition answers them, recording what each was handed."""

    def __init__(self) -> None:
        self.visible: list[frozenset[str]] = []
        self.stopped: list[tuple[str, str]] = []

    def _facts(self) -> list[ActorFacts]:
        return [ActorFacts(adapter="connector.tickets", family="connector", used=Used(days=28))]

    async def register(self, tenant: str, visible: frozenset[str]) -> Any:
        self.visible.append(visible)
        return acting.register(tenant, self._facts(), "eu")

    async def inventory(self, tenant: str, visible: frozenset[str]) -> Any:
        return acting.inventory(await self.register(tenant, visible), AT)

    async def stop(self, tenant: str, adapter: str, actor: str) -> Any:
        if adapter != "connector.tickets":
            raise NotStoppable(f"{adapter!r} is no configured worker, connector or model")
        self.stopped.append((adapter, actor))
        return SimpleNamespace(document=lambda: {"adapter": adapter, "state": "holding"})

    async def remove(self, tenant: str, adapter: str, visible: frozenset[str]) -> Any:
        self.visible.append(visible)
        return acting.remove_view(adapter, None)

    async def residency(self, tenant: str, visible: frozenset[str]) -> Any:
        return acting.residency_view(self._facts(), "eu")

    async def wrong_result(
        self, tenant: str, run_id: str, step_id: str, visible: frozenset[str]
    ) -> Any:
        if run_id != "run_seen":
            return None
        return acting.wrong_result(run_id, step_id, None, [], [])

    async def variants(self, tenant: str, process_id: str) -> Any:
        return v.variants(process_id, "1", ("draft",), v.Travelled(), [], {}, {})


@pytest.fixture
def views(client: Client) -> Views:
    _, given, _ = client
    given.views = Views()
    return given.views  # type: ignore[no-any-return]


PATHS = [
    ("GET", "/register"),
    ("GET", "/register/inventory"),
    ("POST", "/register/connector.tickets/stop"),
    ("GET", "/dependencies/remove/connector.tickets"),
    ("GET", "/dependencies/wrong-result/run_seen/draft"),
    ("GET", "/dependencies/residency"),
    ("GET", "/processes/invoices/variants"),
]


async def reader(given: Services) -> str:
    _, key = await given.identities.add(TENANT, "idn_reader", (TENANT,))
    return key


async def test_every_view_needs_an_account_key(client: Client, views: Views) -> None:
    http, _, base = client
    for method, path in PATHS:
        is_problem(await http.request(method, f"{base}{path}"), 401)


async def test_the_register_is_read_for_the_processes_the_reader_may_see(
    client: Client, views: Views
) -> None:
    http, given, base = client
    await register(given, bundle("1"))
    key = await reader(given)
    answer = await http.get(f"{base}/register", headers=bearer(key))
    assert answer.status_code == 200, answer.text
    assert answer.json()["rows"][0]["adapter"] == "connector.tickets"
    assert views.visible == [frozenset({"invoices"})]
    inventory = (await http.get(f"{base}/register/inventory", headers=bearer(key))).json()
    assert inventory["legally_reviewed"] is False


async def test_the_stop_is_requested_by_the_person_and_an_unknown_adapter_is_refused(
    client: Client, views: Views
) -> None:
    http, given, base = client
    key = await reader(given)
    answer = await http.post(f"{base}/register/connector.tickets/stop", headers=bearer(key))
    assert answer.status_code == 202 and answer.json()["state"] == "holding"
    assert views.stopped == [("connector.tickets", "idn_reader")]
    is_problem(await http.post(f"{base}/register/acme.thing/stop", headers=bearer(key)), 404)


async def test_dependencies_answer_and_a_run_one_may_not_see_is_none(
    client: Client, views: Views
) -> None:
    http, given, base = client
    key = await reader(given)
    removed = await http.get(f"{base}/dependencies/remove/connector.tickets", headers=bearer(key))
    assert removed.status_code == 200 and removed.json()["configured"] is False
    wrong = await http.get(f"{base}/dependencies/wrong-result/run_seen/draft", headers=bearer(key))
    assert wrong.status_code == 200 and "does not compute" in wrong.json()["since_when"]
    is_problem(
        await http.get(f"{base}/dependencies/wrong-result/run_hidden/draft", headers=bearer(key)),
        404,
    )
    where = await http.get(f"{base}/dependencies/residency", headers=bearer(key))
    assert where.json()["rows"][0]["residency"] == "undeclared"


async def test_variants_of_a_process_one_may_not_see_are_answered_as_none(
    client: Client, views: Views
) -> None:
    http, given, base = client
    key = await reader(given)
    is_problem(await http.get(f"{base}/processes/invoices/variants", headers=bearer(key)), 404)
    await register(given, bundle("1"))
    answer = await http.get(f"{base}/processes/invoices/variants", headers=bearer(key))
    assert answer.status_code == 200, answer.text
    assert answer.json()["summary"] == "No run of this process has been recorded yet."
