"""A person's own agent: its key and the rights of the person's roles (ADR-0131 §2, §3).

An agent key proves the identity on the MCP surface and nowhere else, and a new one ends the
one before. A right is granted to a role, never to a person; an identity holds the union of its
roles' rights, read when asked. Every key issued and every right granted or withdrawn is a
ledger entry; granting what is held, or withdrawing what is not, changes nothing.
"""

from __future__ import annotations

import pytest
from fakes.identity import directory

from taktus.components.identity.application.service import UnknownIdentity
from taktus.components.identity.domain.model import Right, RoleRights


async def test_an_agent_key_proves_the_identity_only_as_an_agent_and_a_new_one_ends_it() -> None:
    given = directory()
    _, account_key = await given.person("default", "idn_ada")
    key = await given.directory.issue_agent_key("default", "idn_ada")

    agent = await given.directory.authenticate_agent(key)
    assert agent is not None and agent.identity == "idn_ada"
    assert await given.directory.authenticate(key) is None, "the HTTP surface never takes it"
    assert await given.directory.authenticate_agent(account_key) is None

    again = await given.directory.issue_agent_key("default", "idn_ada")
    assert await given.directory.authenticate_agent(key) is None
    assert await given.directory.authenticate_agent(again) is not None
    assert await given.directory.authenticate(account_key) is not None, "the account key stays"
    with pytest.raises(UnknownIdentity):
        await given.directory.issue_agent_key("default", "idn_nobody")
    assert (await given.kinds("default")).count("identity.agent_key_issued") == 2


async def test_an_identity_holds_the_rights_of_its_roles_as_they_are_now() -> None:
    given = directory()
    await given.directory.add("default", "idn_ada", ("default",), roles=("ops", "finance.lead"))
    await given.directory.add("default", "idn_bo", ("default",), roles=("ops",))
    ada = await given.directory.identity("default", "idn_ada")
    bo = await given.directory.identity("default", "idn_bo")
    assert ada is not None and bo is not None
    assert await given.directory.rights(ada) == frozenset()

    await given.directory.grant("default", "ops", Right.START, by="idn_admin")
    await given.directory.grant("default", "finance.lead", Right.ANSWER, by="idn_admin")
    assert await given.directory.rights(ada) == {Right.START, Right.ANSWER}
    assert await given.directory.rights(bo) == {Right.START}

    await given.directory.withdraw("default", "ops", Right.START, by="idn_admin")
    assert await given.directory.rights(bo) == frozenset()
    assert await given.directory.granted("default") == [
        RoleRights(id="finance.lead", tenant="default", rights=(Right.ANSWER,))
    ]


async def test_every_grant_and_withdrawal_is_an_entry_and_a_repeat_changes_nothing() -> None:
    given = directory()
    await given.directory.grant("default", "ops", Right.TAKE_OVER, by="idn_admin")
    await given.directory.grant("default", "ops", Right.TAKE_OVER, by="idn_admin")
    await given.directory.withdraw("default", "ops", Right.START, by="idn_admin")
    await given.directory.withdraw("default", "ops", Right.TAKE_OVER, by="idn_admin")
    kinds = [k for k in await given.kinds("default") if k.startswith("identity.right")]
    assert kinds == ["identity.right_granted", "identity.right_withdrawn"]
    async with given.persistence.transaction("default"):
        entries = await given.ledger.entries("default")
    assert {e.refs.actor for e in entries if e.kind.startswith("identity.right")} == {"idn_admin"}
