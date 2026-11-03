"""`taktusctl catalogue` (ADR-0175, UC-14.6): an author signs an index, an operator trusts the
author's key for one tier, and the instance installs only what it verified.

An image is installed as an adapter identifier and printed by digest; a community bundle becomes
a proposal at level 2 or below and is refused above; an unsigned entry, an entry by a key the
operator does not trust, a key used for the wrong tier and a bundle changed after it was signed
are each refused with the reason, and nothing of them is recorded. An index that states
*verified* is refused whole. Every installation is in the ledger with its tier and its origin.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from taktus.composition.local import LocalWiring

from .test_first_slice import PLAIN, taktusctl

TENANT = "default"
WHO = "idn_ada"

BUNDLE: dict[str, Any] = {
    "id": "order-note",
    "version": "1",
    "name": "A note on a received order",
    "autonomy": {
        "level": 2,
        "reason": "a community bundle: a person confirms each step before it starts",
        "toward_next": "a run of notes a person read and did not have to correct",
    },
    "author": "an author of the community",
    "reason": "a note on every order received, by a fixed form of words",
    "limits": {"compute": {"seconds": 10, "resource_class": "cpu.small"}},
    "inputs": {"order": {"description": "The order's number", "example": "A-17"}},
    "steps": [
        {
            "id": "write",
            "method": "rule",
            "reason": "the note is a fixed form of words filled in with the order's number",
            "rejected": [{"method": "llm", "why": "a fixed form of words needs no model"}],
            "exactness": "exact",
            "checks": [{"kind": "recomputation", "subject": "the note"}],
            "work": {
                "rule": "template",
                "text": "Order ${order} was received.",
                "values": {"order": {"$input": "order"}},
            },
        }
    ],
}


def catalogue(
    state: Path, environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "catalogue", *arguments],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN, "TAKTUS_STATE_DIR": str(state), **environment},
        check=False,
    )


def image(entry_id: str, tier: str) -> dict[str, Any]:
    return {
        "id": entry_id,
        "kind": "image",
        "tier": tier,
        "version": "0.1.0",
        "summary": "Runs a shell script as a worker step.",
        "digest": "sha256:" + "b" * 64,
        "family": "worker",
        "contract": "worker/v1",
        "capabilities": ["shell.script"],
        "image": f"registry.example/acme/{entry_id}",
    }


def bundle_entry(entry_id: str, file: str) -> dict[str, Any]:
    return {
        "id": entry_id,
        "kind": "bundle",
        "tier": "community",
        "version": "1",
        "summary": "A note on every order received.",
        "digest": "sha256:" + "0" * 64,
        "process": "order-note",
        "bundle": file,
    }


def test_an_instance_installs_only_what_it_verified_and_records_where_it_came_from(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    added = subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "identity", "add", WHO, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )
    assert added.returncode == 0, added.stdout + added.stderr

    author = tmp_path / "author.seed"
    author.write_bytes(os.urandom(32))
    stranger = tmp_path / "stranger.seed"
    stranger.write_bytes(os.urandom(32))

    directory = tmp_path / "catalogue"
    (directory / "bundles").mkdir(parents=True)
    (directory / "bundles" / "order-note.yaml").write_text(yaml.safe_dump(BUNDLE), "utf-8")
    raised = {**BUNDLE, "autonomy": {**BUNDLE["autonomy"], "level": 3}}
    (directory / "bundles" / "order-note-3.yaml").write_text(yaml.safe_dump(raised), "utf-8")
    index = directory / "acme.json"
    index.write_text(
        json.dumps(
            {
                "catalogue": "acme",
                "entries": [
                    image("worker-shell", "community"),
                    image("worker-claimed", "reference"),
                    bundle_entry("order-note", "bundles/order-note.yaml"),
                    bundle_entry("order-note-raised", "bundles/order-note-3.yaml"),
                ],
            }
        ),
        "utf-8",
    )
    environment: dict[str, str] = {}
    signed = catalogue(state, environment, "sign", str(index), "--seed-file", str(author))
    assert signed.returncode == 0, signed.stdout + signed.stderr
    assert signed.stdout.split() == [
        "signed",
        "worker-shell",
        "signed",
        "worker-claimed",
        "signed",
        "order-note",
        "signed",
        "order-note-raised",
    ]
    assert author.read_bytes().hex() not in index.read_text("utf-8"), "the seed stays its own"

    # Another index: one entry by a stranger, one unsigned, and an index that states verified.
    foreign = json.loads(index.read_text("utf-8"))["entries"][0]
    stranger_index = directory / "stranger.json"
    stranger_index.write_text(
        json.dumps({"catalogue": "stranger", "entries": [image("worker-other", "community")]}),
        "utf-8",
    )
    assert (
        catalogue(
            state, environment, "sign", str(stranger_index), "--seed-file", str(stranger)
        ).returncode
        == 0
    )
    unsigned = {**image("worker-unsigned", "community")}
    (directory / "unsigned.json").write_text(
        json.dumps({"catalogue": "unsigned", "entries": [unsigned]}), "utf-8"
    )
    (directory / "claims.json").write_text(
        json.dumps({"catalogue": "claims", "entries": [{**foreign, "tier": "verified"}]}), "utf-8"
    )

    key = catalogue(state, environment, "key", "--seed-file", str(author))
    assert key.returncode == 0 and len(key.stdout.strip()) == 43
    trust = tmp_path / "trust.json"
    trust.write_text(
        json.dumps({"keys": [{"key": key.stdout.strip(), "tier": "community", "author": "acme"}]}),
        "utf-8",
    )
    environment = {
        "TAKTUS_CATALOGUE_DIRECTORY": str(directory),
        "TAKTUS_CATALOGUE_KEYS": str(trust),
    }

    listed = catalogue(state, environment, "list")
    assert listed.returncode == 0, listed.stderr
    text = listed.stdout
    assert "acme/worker-shell 0.1.0  image  community  admitted" in text
    assert "acme/worker-claimed 0.1.0  image  reference  refused" in text
    assert "trusted for the community tier, and the entry states reference" in text
    assert "stranger/worker-other 0.1.0  image  community  refused" in text
    assert "is not one the operator trusts" in text
    assert "unsigned/worker-unsigned 0.1.0  image  community  refused" in text
    assert "refused: the entry is not signed" in text
    assert "claims.json  refused: not an index by contract catalogue/v1" in text

    for refused in ("acme/worker-claimed", "stranger/worker-other", "unsigned/worker-unsigned"):
        attempt = catalogue(
            state, environment, "install", refused, "--as", "worker.shell", "--identity", WHO
        )
        assert attempt.returncode == 1, (refused, attempt.stdout, attempt.stderr)
        assert f"refused: {refused}\n" in attempt.stderr

    wrong = catalogue(
        state, environment, "install", "acme/worker-shell", "--as", "connector.shell",
        "--identity", WHO,
    )  # fmt: skip
    assert wrong.returncode == 1 and "a worker is installed as worker.<name>" in wrong.stderr

    installed = catalogue(
        state, environment, "install", "acme/worker-shell", "--as", "worker.shell",
        "--identity", WHO,
    )  # fmt: skip
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert "installed acme/worker-shell as worker.shell, community, signed by acme" in (
        installed.stdout
    )
    assert f"pull by digest: registry.example/acme/worker-shell@sha256:{'b' * 64}" in (
        installed.stdout
    )
    assert "ledger: catalogue.installed" in installed.stdout

    above = catalogue(state, environment, "install", "acme/order-note-raised", "--identity", WHO)
    assert above.returncode == 1
    assert "a community bundle is installed at level 2 or below" in above.stderr

    proposed = catalogue(state, environment, "install", "acme/order-note", "--identity", WHO)
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    assert "for order-note@1: a person decides" in proposed.stdout

    # The bundle changes after it was signed: refused, and nothing more is recorded.
    changed = {**BUNDLE, "name": "Another note"}
    (directory / "bundles" / "order-note.yaml").write_text(yaml.safe_dump(changed), "utf-8")
    tampered = catalogue(state, environment, "install", "acme/order-note", "--identity", WHO)
    assert tampered.returncode == 1
    assert "is not the one it was signed over" in tampered.stderr

    after = catalogue(state, environment, "list")
    assert "installed as worker.shell, community here" in after.stdout
    assert "missing: the conformance suite has not been recorded as passed" in after.stdout

    async def recorded() -> list[Any]:
        async with LocalWiring().services(
            state_dir=state, worker_endpoint="http://127.0.0.1:1"
        ) as services:
            async with services.work.transaction(TENANT):
                assert (await services.ledger.verify(TENANT)).intact
                return list(await services.ledger.of_kinds(TENANT, ["catalogue.installed"]))

    entries = asyncio.run(recorded())
    assert [(e.adapter, e.outcome, e.refs.actor) for e in entries] == [
        ("worker.shell", "community", WHO),
        (None, "community", WHO),
    ]
    assert entries[1].refs.process_version == "order-note@1"
    assert all(e.content_digest for e in entries)
