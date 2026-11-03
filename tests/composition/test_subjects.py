"""Data-protection requests answered from what references their subject (UC-11.2, ADR-0176).

Two cases run through the same process, one for each of two customers. Each run reads its
customer's account in a scoped step and sets a flag whose value is the same in both — one
object of the store, held by both runs. A worker's trace is kept for each account step. A
request names one customer: it finds that customer's run and nothing of the other's, and a
person carries it out.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from components.run.test_case_scope import ACCOUNT, MAIL, SCOPE, Scoped, step
from components.run.test_engine import AT, TENANT, rule

from taktus.adapters.driven.memory import MemoryRepository
from taktus.adapters.driven.memory.tenant_store import MemoryTenantStore
from taktus.adapters.driven.memory.trace_store import MemoryTraceStore
from taktus.components.governance.application.service import (
    PrepareRequest,
    SubjectRequests,
)
from taktus.components.governance.domain.model import (
    RequestKind,
    RequestRefused,
    RequestState,
    SubjectRequest,
)
from taktus.components.governance.domain.model.subjects import ERASED, KEPT_SHARED
from taktus.components.run.domain.model import Run, RunState
from taktus.components.run.domain.service.provenance import verify
from taktus.composition.subjects import RunHoldings
from taktus.ports.traces import TraceLine
from taktus.shared.v1 import Step

WORKER_SAID = "read the account of the customer, plan team"


class Case:
    def __init__(self, *more: tuple[Step, dict[str, Any]]) -> None:
        self.h = Scoped(
            step("account", ACCOUNT, {"account": {"$input": "customer"}}, scope=SCOPE),
            rule("flag", {"rule": "constant", "value": {"ok": True}}),
            *more,
        )
        self.traces = MemoryTraceStore(self.h.persistence)
        self.holdings = RunHoldings(
            runs=self.h.runs,
            provenance=self.h.provenance,
            ledger=self.h.ledger,
            objects=self.h.objects,
            work=self.h.persistence,
            tenants=MemoryTenantStore(self.h.persistence),
            traces=self.traces,
            locations=self._locations,
        )
        self.requests = SubjectRequests(
            MemoryRepository(self.h.persistence, SubjectRequest),
            self.holdings,
            self.h.ledger,
            self.h.persistence,
            self.h.clock,
            self.h.ids,
        )

    async def _locations(self, tenant: str) -> dict[str, str | None]:
        return {"connector.customers": "eu"}

    async def run(self, customer: str) -> Run:
        run = await self.h.begin(customer=customer)
        assert run.state is RunState.FINISHED, run.reason
        async with self.h.persistence.transaction(TENANT):
            await self.traces.append(
                TENANT,
                TraceLine(
                    run_id=run.id,
                    step_id="account",
                    assignment_id="asg_1",
                    seq=1,
                    ts=AT,
                    type="progress",
                    detail={"text": f"{WORKER_SAID} ({customer})"},
                    recorded_at=AT,
                ),
            )
        return run

    async def stored(self, run_id: str) -> Run:
        async with self.h.persistence.transaction(TENANT):
            found = await self.h.runs.get(TENANT, run_id)
        assert found is not None
        return found

    async def lines(self, run_id: str) -> int:
        async with self.h.persistence.transaction(TENANT):
            return len(await self.traces.lines(TENANT, run_id, "account", limit=100))

    async def everything_recorded(self) -> str:
        async with self.h.persistence.transaction(TENANT):
            entries = await self.h.ledger.entries(TENANT)
        return json.dumps([e.document() for e in entries], default=str)

    async def prepare(self, kind: RequestKind, subject: str = "cust-1") -> SubjectRequest:
        return await self.requests.prepare(
            PrepareRequest(tenant=TENANT, kind=kind, subject=subject), by="idn_dpo"
        )


def _result(run: Run, step_id: str) -> str:
    checkpoint = run.step_run(step_id).checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    return checkpoint.result_digest


# --- finding ---------------------------------------------------------------------------------


async def test_a_request_finds_every_holding_of_its_subject_and_none_of_another_s() -> None:
    case = Case()
    first, second = await case.run("cust-1"), await case.run("cust-2")
    request = await case.prepare(RequestKind.ERASURE)
    (holding,) = request.holdings
    assert holding.run_id == first.id and holding.run_id != second.id
    assert holding.found_through == ("provenance", "intake")
    assert holding.inputs == ("customer",) and holding.ended
    by_step = {s.step_id: s for s in holding.steps}
    assert by_step["account"].scoped and by_step["account"].recorded
    assert by_step["account"].trace_lines == 1 and by_step["flag"].trace_lines == 0
    digests = {o.digest: o for o in holding.objects}
    assert _result(first, "account") in digests
    assert _result(second, "account") not in digests
    assert digests[_result(first, "account")].kept is None
    # The flag's bytes are the same in both runs: one object, which the other run still needs.
    assert _result(first, "flag") == _result(second, "flag")
    assert digests[_result(first, "flag")].kept == KEPT_SHARED
    assert request.state is RequestState.PREPARED and request.prepared_by == "idn_dpo"


async def test_a_run_whose_scoped_step_has_not_completed_is_found_through_its_intake() -> None:
    case = Case()
    run = await case.run("cust-1")
    stored = await case.stored(run.id)
    async with case.h.persistence.transaction(TENANT):
        await case.h.runs.put(TENANT, stored.model_copy(update={"id": "run_open"}))
    request = await case.prepare(RequestKind.ACCESS)
    found = {h.run_id: h.found_through for h in request.holdings}
    assert found == {run.id: ("provenance", "intake"), "run_open": ("intake",)}


async def test_preparing_changes_nothing_and_names_the_request_never_the_subject() -> None:
    case = Case()
    run = await case.run("cust-1")
    request = await case.prepare(RequestKind.ERASURE)
    assert (await case.stored(run.id)).inputs == {"customer": "cust-1"}
    assert await case.h.objects.get(_result(run, "account")) is not None
    assert await case.lines(run.id) == 1
    async with case.h.persistence.transaction(TENANT):
        (entry,) = await case.h.ledger.of_kinds(TENANT, ["subject.request_prepared"])
    assert entry.refs.subject_request_id == request.id and entry.outcome == "erasure"
    assert entry.refs.actor == "idn_dpo"
    # The provenance record names the customer, as ADR-0130 §7 asks; the request's entries
    # do not.
    assert "cust-1" not in json.dumps(entry.document(), default=str)


# --- confirming ------------------------------------------------------------------------------


async def test_a_confirmation_without_the_identity_check_is_refused_and_changes_nothing() -> None:
    case = Case()
    run = await case.run("cust-1")
    request = await case.prepare(RequestKind.ERASURE)
    with pytest.raises(RequestRefused, match="checked the requester's identity"):
        await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=False)
    assert (await case.stored(run.id)).inputs == {"customer": "cust-1"}
    again = await case.requests.get(TENANT, request.id)
    assert again is not None and again.state is RequestState.PREPARED


async def test_a_request_whose_holdings_changed_since_it_was_prepared_is_refused() -> None:
    case = Case()
    await case.run("cust-1")
    request = await case.prepare(RequestKind.ERASURE)
    later = await case.run("cust-1")
    with pytest.raises(RequestRefused, match="changed since"):
        await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    assert (await case.stored(later.id)).inputs == {"customer": "cust-1"}


async def test_a_withdrawn_request_is_never_carried_out() -> None:
    case = Case()
    run = await case.run("cust-1")
    request = await case.prepare(RequestKind.ERASURE)
    withdrawn = await case.requests.withdraw(TENANT, request.id, by="idn_dpo")
    assert withdrawn.state is RequestState.WITHDRAWN
    async with case.h.persistence.transaction(TENANT):
        (entry,) = await case.h.ledger.of_kinds(TENANT, ["subject.request_withdrawn"])
    assert (entry.refs.subject_request_id, entry.refs.actor) == (request.id, "idn_dpo")
    with pytest.raises(RequestRefused, match="withdrawn"):
        await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    assert (await case.stored(run.id)).inputs == {"customer": "cust-1"}


# --- erasing ---------------------------------------------------------------------------------


async def test_an_erasure_removes_the_content_and_every_chain_still_verifies() -> None:
    case = Case()
    first, second = await case.run("cust-1"), await case.run("cust-2")
    request = await case.prepare(RequestKind.ERASURE)
    done = await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    assert done.export is None
    erased = done.request.outcome and done.request.outcome.erased
    assert erased is not None
    assert erased.runs == (first.id,) and erased.pending == ()
    assert erased.ledger_intact and erased.provenance_intact, erased.findings
    assert erased.inputs_erased == 1 and erased.trace_lines_erased == 1
    assert erased.objects_kept == 1 and erased.objects_removed >= 1
    # The subject's content is gone ...
    assert (await case.stored(first.id)).inputs == {"customer": ERASED}
    assert await case.h.objects.get(_result(first, "account")) is None
    assert await case.lines(first.id) == 0
    # ... what another run still references is kept, and the other subject is untouched.
    assert await case.h.objects.get(_result(first, "flag")) is not None
    assert (await case.stored(second.id)).inputs == {"customer": "cust-2"}
    assert await case.h.objects.get(_result(second, "account")) is not None
    assert await case.lines(second.id) == 1
    # The record of what happened verifies, from its first entry and per run.
    async with case.h.persistence.transaction(TENANT):
        assert (await case.h.ledger.verify(TENANT, full=True)).intact
        records = await case.h.provenance.of_run(TENANT, first.id)
        entries = await case.h.ledger.entries(TENANT, first.id)
    assert verify(await case.stored(first.id), records, entries).intact
    kinds = [e.kind for e in entries]
    assert kinds[-1] == "run.content_erased"
    assert entries[-1].refs.subject_request_id == request.id
    recorded = await case.everything_recorded()
    assert '"subject.erased"' in recorded and '"verified"' in recorded
    assert "cust-1" not in recorded and WORKER_SAID not in recorded
    assert done.request.state is RequestState.CARRIED_OUT
    assert done.request.carried_out_by == "idn_dpo" and done.request.identity_checked
    with pytest.raises(RequestRefused, match="carried_out, not prepared"):
        await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)


async def test_an_erased_run_is_found_again_as_erased_and_holds_no_input() -> None:
    case = Case()
    run = await case.run("cust-1")
    request = await case.prepare(RequestKind.ERASURE)
    await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    (holding,) = (await case.prepare(RequestKind.ACCESS)).holdings
    assert holding.run_id == run.id and holding.found_through == ("provenance",)
    assert holding.erased_for == request.id and holding.inputs == ()


async def test_a_run_in_flight_is_not_erased_and_is_named_pending() -> None:
    case = Case()
    run = await case.run("cust-1")
    stored = await case.stored(run.id)
    async with case.h.persistence.transaction(TENANT):
        await case.h.runs.put(TENANT, stored.model_copy(update={"state": RunState.RUNNING}))
    request = await case.prepare(RequestKind.ERASURE)
    done = await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    erased = done.request.outcome and done.request.outcome.erased
    assert erased is not None and erased.runs == () and erased.pending == (run.id,)
    assert (await case.stored(run.id)).inputs == {"customer": "cust-1"}
    assert await case.h.objects.get(_result(run, "account")) is not None


# --- exporting -------------------------------------------------------------------------------


async def test_an_access_export_carries_the_content_and_its_processing_and_is_not_stored() -> None:
    case = Case()
    run = await case.run("cust-1")
    await case.run("cust-2")
    request = await case.prepare(RequestKind.ACCESS)
    done = await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    assert done.export is not None
    document: dict[str, Any] = json.loads(done.export)
    assert document["kind"] == "access" and document["subject"] == "cust-1"
    (exported,) = document["runs"]
    assert exported["run"] == run.id and exported["inputs"] == {"customer": "cust-1"}
    steps = {s["step"]: s for s in exported["steps"]}
    assert steps["account"]["result"]["json"]["output"] == {"id": "cust-1", "plan": "team"}
    assert steps["account"]["processing"] == {"adapter": "connector.customers", "location": "eu"}
    assert steps["account"]["trace"][0]["detail"]["text"].startswith(WORKER_SAID)
    assert {k["record"] for k in document["keeping"]} >= {"ledger", "trace", "run content"}
    assert "cust-2" not in done.export.decode()
    outcome = done.request.outcome and done.request.outcome.exported
    assert outcome is not None
    assert await case.h.objects.get(outcome.digest) is None, "an export is never stored"
    async with case.h.persistence.transaction(TENANT):
        (entry,) = await case.h.ledger.of_kinds(TENANT, ["subject.exported"])
    assert entry.content_digest == outcome.digest and entry.outcome == "access"


async def test_a_portability_export_carries_the_data_alone() -> None:
    case = Case()
    await case.run("cust-1")
    request = await case.prepare(RequestKind.PORTABILITY)
    done = await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    assert done.export is not None
    document = json.loads(done.export)
    assert "keeping" not in document
    assert all("processing" not in s for r in document["runs"] for s in r["steps"])


# --- rectifying ------------------------------------------------------------------------------


async def test_a_rectification_lists_what_to_correct_and_rewrites_nothing() -> None:
    # The case answers the customer by mail: that answer left the system (ADR-0022).
    case = Case(step("notify", MAIL, {"to": {"$input": "customer"}}, after=("account",)))
    run = await case.run("cust-1")
    request = await case.prepare(RequestKind.RECTIFICATION)
    (holding,) = request.holdings
    assert holding.left_the_system >= 1 and holding.built_on == ()
    done = await case.requests.confirm(TENANT, request.id, by="idn_dpo", identity_checked=True)
    assert done.export is None and done.request.state is RequestState.CARRIED_OUT
    assert (await case.stored(run.id)).inputs == {"customer": "cust-1"}
    assert await case.h.objects.get(_result(run, "account")) is not None
    async with case.h.persistence.transaction(TENANT):
        (entry,) = await case.h.ledger.of_kinds(TENANT, ["subject.rectified"])
    assert entry.outcome == "confirmed" and entry.refs.actor == "idn_dpo"


async def test_a_request_names_a_subject() -> None:
    case = Case()
    with pytest.raises(RequestRefused, match="names its subject"):
        await case.prepare(RequestKind.ACCESS, subject="  ")
    assert case.h.clock.now() - AT < timedelta(days=1)
