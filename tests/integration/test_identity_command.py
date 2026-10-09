"""`taktusctl identity`: an administrator adds identities, sees every link of a tenant and
revokes one; the next event from a revoked account is from an unknown sender (UC-1.7,
ADR-0040). The link itself is made the only way there is: by the person, with a code."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from taktus.composition.local import LocalWiring

from .test_first_slice import PLAIN, taktusctl


def identity(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "identity", *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_administrator_adds_sees_and_revokes_and_never_links(tmp_path: Path) -> None:
    state = tmp_path / "state"
    added = identity(state, "add", "idn_ada", "--org-path", "default/finance")
    assert added.returncode == 0, added.stdout + added.stderr
    assert "account key, shown once" in added.stdout
    key = added.stdout.rsplit(" ", 1)[-1].strip()
    assert key.startswith("tka_")
    assert key not in "".join(p.read_text() for p in state.glob("*.json")), "only a digest"

    again = identity(state, "add", "idn_ada", "--org-path", "default/finance")
    assert again.returncode == 0 and "unchanged" in again.stdout and "tka_" not in again.stdout
    other = identity(state, "add", "idn_ada", "--org-path", "default/sales")
    assert other.returncode == 2 and "already" in other.stderr
    elsewhere = identity(state, "add", "idn_bob", "--tenant", "acme")
    assert elsewhere.returncode == 2 and "serves no tenant 'acme'" in elsewhere.stderr

    assert "has no links" in identity(state, "links").stdout

    async def link() -> None:
        async with LocalWiring().services(
            state_dir=state, worker_endpoint="http://127.0.0.1:1"
        ) as services:
            who = await services.identities.authenticate(key)
            assert who is not None and who.org_path == ("default", "finance")
            code, _ = await services.identities.create_link_code(who, "channel.repo")
            answer = await services.identities.unknown_sender("channel.repo", "100200", code)
            assert answer.linked is not None

    asyncio.run(link())
    listed = identity(state, "links")
    assert "channel.repo  100200  →  idn_ada  (confirmed" in listed.stdout
    assert "active" in listed.stdout
    link_id = listed.stdout.split()[0]

    revoked = identity(state, "revoke", link_id, "--identity", "idn_admin")
    assert revoked.returncode == 0 and "nobody's now" in revoked.stdout
    assert "revoked" in identity(state, "links").stdout
    assert identity(state, "revoke", link_id).returncode == 2, "revoked once"

    async def placed() -> None:
        async with LocalWiring().services(
            state_dir=state, worker_endpoint="http://127.0.0.1:1"
        ) as services:
            assert await services.identities.resolve("channel.repo", "100200") is None

    asyncio.run(placed())

    new_key = identity(state, "key", "idn_ada")
    assert new_key.returncode == 0 and "tka_" in new_key.stdout
    assert new_key.stdout.rsplit(" ", 1)[-1].strip() != key
