"""The ledger exported, and verified outside Taktus (UC-6.1, ADR-0253 §1, §2).

The backup program imports nothing of Taktus. Its `verify-export` walks the file an export
wrote — one entry per line — by the ledger's published rule. The entries here are Taktus's own:
run chains, the tenant's chain and an anchor over the run chains' heads. An intact export
verifies; a field altered, an alteration whose own hash was recomputed, a line removed and two
lines swapped are each found, as Taktus's own verification finds them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fakes import FakeClock

from deploy.backup_program import backup
from taktus.adapters.driven.memory import MemoryLedgerStore, MemoryPersistence
from taktus.components.ledger.application.service import ChainedLedger
from taktus.components.ledger.domain.model import canonical, exported
from taktus.ports.ledger import Fact
from taktus.shared.v1 import LedgerRefs

TENANT = "t"


async def entries_written() -> list[bytes]:
    persistence = MemoryPersistence()
    ledger = ChainedLedger(MemoryLedgerStore(persistence), FakeClock())
    async with persistence.transaction(TENANT):
        for run in ("run_1", "run_2"):
            for kind, outcome in (("run.created", None), ("run.finished", "finished")):
                await ledger.record(
                    TENANT,
                    Fact(
                        kind=kind,
                        refs=LedgerRefs(tenant=TENANT, run_id=run, process_version="p@1"),
                        outcome=outcome,
                    ),
                )
        await ledger.record(
            TENANT, Fact(kind="process.registered", refs=LedgerRefs(tenant=TENANT), outcome="ok")
        )
        anchored = await ledger.anchor(TENANT)
        assert anchored is not None
        assert (await ledger.verify(TENANT, full=True)).intact
        written = exported(await ledger.entries(TENANT))
    return written.splitlines(keepends=True)


def verified(tmp_path: Path, lines: list[bytes], capsys: pytest.CaptureFixture[str]) -> int:
    path = tmp_path / "ledger.ndjson"
    path.write_bytes(b"".join(lines))
    code = backup.main(["verify-export", str(path)], env={})
    capsys.readouterr()
    return code


async def test_an_export_verifies_outside_taktus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = await entries_written()
    path = tmp_path / "ledger.ndjson"
    path.write_bytes(b"".join(lines))
    assert backup.main(["verify-export", str(path)], env={}) == 0
    said = capsys.readouterr().out
    assert f"{len(lines)} entries" in said and "intact" in said
    for line in lines:
        document = json.loads(line)
        assert set(document) <= set(backup.LEDGER_FIELDS), "no field the hash rule leaves out"


async def test_every_alteration_of_an_export_is_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = await entries_written()

    def altered(index: int, *, rehash: bool) -> list[bytes]:
        document = json.loads(lines[index])
        document["outcome"] = "escalated"
        if rehash:
            document["hash"] = "sha256:" + hashlib.sha256(canonical(document)).hexdigest()
        changed = list(lines)
        changed[index] = (json.dumps(document, sort_keys=True) + "\n").encode()
        return changed

    finished = next(i for i, line in enumerate(lines) if b'"run.finished"' in line)
    assert verified(tmp_path, altered(finished, rehash=False), capsys) == 1
    # Its own hash recomputed: the next entry of its chain, or the anchor over it, finds it.
    first_finished = next(i for i, line in enumerate(lines) if b'"run.created"' in line)
    assert verified(tmp_path, altered(first_finished, rehash=True), capsys) == 1
    assert verified(tmp_path, lines[:1] + lines[2:], capsys) == 1, "a line removed"
    assert verified(tmp_path, [lines[1], lines[0], *lines[2:]], capsys) == 1, "two swapped"


def test_a_file_that_is_no_export_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "ledger.ndjson"
    path.write_text('{"kind": "no entry"}\n', encoding="utf-8")
    assert backup.main(["verify-export", str(path)], env={}) == 1
    assert "no ledger entry" in capsys.readouterr().err
