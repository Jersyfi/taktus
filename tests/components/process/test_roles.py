"""A human step and a fallback to a person name a role, never a person (UC-4.20, ADR-0146).

Registration refuses a person's step without a role once the tenant has a structure — once an
identity of the tenant holds a role — and one naming a role nobody holds. While no role is
held, nothing is required."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeClock
from pydantic import ValidationError

from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence, MemoryRepository
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.process.application.service.register_version import (
    RegisterProcessVersion,
    RegisterProcessVersionHandler,
)
from taktus.components.process.domain.model import InvalidProcess, Process, ProcessVersion
from taktus.shared.v1 import Step

TENANT = "t"


class Structure:
    def __init__(self, *roles: str) -> None:
        self._roles = frozenset(roles)

    async def roles(self, tenant: str) -> frozenset[str]:
        return self._roles


def handler(*roles: str) -> RegisterProcessVersionHandler:
    clock = FakeClock(datetime(2026, 10, 28, 9, 0, tzinfo=UTC))
    persistence = MemoryPersistence()
    return RegisterProcessVersionHandler(
        MemoryRepository(persistence, ProcessVersion),
        persistence,
        MemoryRepository(persistence, Process),
        ledger=ChainedLedger(MemoryLedgerStore(persistence), clock),
        clock=clock,
        structure=Structure(*roles),
    )


def approve(**named: Any) -> dict[str, Any]:
    return {
        "id": "approve",
        "method": "human",
        "reason": "paying binds the organisation",
        "rejected": [],
        **named,
    }


def classify(**fallback: Any) -> dict[str, Any]:
    return {
        "id": "classify",
        "method": "llm",
        "reason": "free text",
        "rejected": [],
        "exactness": "tolerant",
        "model": None,
        "fallback": {"when": "confidence < 0.8", "to": "human", **fallback},
        "work": {"purpose": "classification", "prompt": "Classify."},
    }


def bundle(*steps: dict[str, Any]) -> dict[str, Any]:
    cleaned = [{k: v for k, v in step.items() if v is not None} for step in steps]
    return {
        "id": "paid",
        "version": "1",
        "name": "paid",
        "autonomy": {"level": 1, "reason": "a test", "toward_next": "nothing"},
        "steps": cleaned,
    }


async def test_without_a_structure_a_human_step_registers_without_a_role() -> None:
    version = await handler().execute(
        RegisterProcessVersion(bundle=bundle(approve()), tenant=TENANT)
    )
    assert version.ref == "paid@1"


async def test_with_a_structure_a_human_step_without_a_role_is_refused_naming_the_roles() -> None:
    with pytest.raises(InvalidProcess, match=r"'approve': a human step names the role") as raised:
        await handler("accounts-approver").execute(
            RegisterProcessVersion(bundle=bundle(approve()), tenant=TENANT)
        )
    assert "accounts-approver" in str(raised.value)


async def test_a_fallback_to_a_person_without_a_role_is_refused_once_there_is_a_structure() -> None:
    with pytest.raises(InvalidProcess, match=r"'classify': its fallback to a person names"):
        await handler("support-lead").execute(
            RegisterProcessVersion(bundle=bundle(classify()), tenant=TENANT)
        )


async def test_a_role_no_identity_holds_is_refused() -> None:
    with pytest.raises(InvalidProcess, match=r"names the role 'cfo', which no identity"):
        await handler("accounts-approver").execute(
            RegisterProcessVersion(bundle=bundle(approve(role="cfo")), tenant=TENANT)
        )


async def test_a_human_step_and_a_fallback_naming_held_roles_register() -> None:
    given = bundle(
        approve(role="accounts-approver", expertise=["the cost centre's budget"]),
        {**classify(role="support-lead"), "depends_on": ["approve"]},
    )
    version = await handler("accounts-approver", "support-lead").execute(
        RegisterProcessVersion(bundle=given, tenant=TENANT)
    )
    steps = {s.id: s for s in version.steps}
    assert steps["approve"].performer == "accounts-approver"
    assert steps["approve"].expertise == ("the cost centre's budget",)
    assert steps["classify"].performer == "support-lead"


@pytest.mark.parametrize(
    ("step", "why"),
    [
        (
            {"method": "rule", "exactness": "sourced", "role": "bookkeeper"},
            "a rule step names no role",
        ),
        ({"method": "human", "expertise": ["x"]}, "expertise needs its role"),
        (
            {
                "method": "llm",
                "exactness": "free",
                "fallback": {"when": "x", "to": "llm", "role": "editor"},
            },
            "only one to a person does",
        ),
        ({"method": "human", "role": "Jane Doe"}, "string_pattern_mismatch"),
    ],
)
def test_a_role_belongs_only_to_where_a_person_acts(step: dict[str, Any], why: str) -> None:
    with pytest.raises(ValidationError, match=why):
        Step.model_validate({"id": "s", "reason": "r", "rejected": [], **step})
