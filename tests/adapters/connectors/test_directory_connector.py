"""The directory connector: `knowledge.pages` over a directory of Markdown files, the knowledge
system of an organisation that has none (UC-13.6 §3, ADR-0065)."""

from __future__ import annotations

from pathlib import Path

import pytest

from taktus.adapters.driven.connectors.directory import (
    DECLARATION,
    LIST,
    READ,
    WRITE,
    DirectoryConnector,
    digest,
)
from taktus.ports.connector import CallContext, CallFailed, Cause, idempotency_key

PLACE = ["Taktus", "Administration", "Installing"]
BODY = "# Installing\n\nRun it.\n"


def context(step: str = "write") -> CallContext:
    return CallContext(
        tenant="default",
        identity="idn_operator",
        run_id="run_guides",
        step_id=step,
        attempt=1,
        idempotency_key=idempotency_key("run_guides", step, 1),
        credentials=(),
    )


async def write(
    connector: DirectoryConnector,
    body: str = BODY,
    expected: str | None = None,
    step: str = "write",
) -> dict[str, object]:
    result = await connector.call(
        WRITE, context(step), {"place": PLACE, "body": body, "mark": "m1", "expected": expected}
    )
    return {"output": result.output, "replayed": result.effect.replayed}


def test_it_declares_the_capability_and_a_marked_write() -> None:
    assert DECLARATION.capabilities == ("knowledge.pages",)
    operation = DECLARATION.operation(WRITE)
    assert operation is not None and operation.repeatable


async def test_a_page_is_a_file_that_shows_the_page_and_keeps_its_mark_out_of_sight(
    tmp_path: Path,
) -> None:
    connector = DirectoryConnector(tmp_path)
    written = await write(connector)
    path = tmp_path / "Taktus" / "Administration" / "Installing.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith(BODY)
    assert text.splitlines()[-1].startswith("<!-- taktus ")
    assert written == {"output": {"place": PLACE, "digest": digest(BODY)}, "replayed": False}
    read = await connector.call(READ, context("read"), {"place": PLACE})
    assert read.output == {"place": PLACE, "body": BODY, "digest": digest(BODY), "mark": "m1"}
    listed = await connector.call(LIST, context("list"), {"place": ["Taktus"]})
    assert listed.output == {"pages": [{"place": PLACE, "digest": digest(BODY), "mark": "m1"}]}


async def test_a_hand_edit_of_the_file_changes_the_digest_and_keeps_the_mark(
    tmp_path: Path,
) -> None:
    connector = DirectoryConnector(tmp_path)
    await write(connector)
    path = tmp_path / "Taktus" / "Administration" / "Installing.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Run it.", "Run it twice."))
    read = await connector.call(READ, context("read"), {"place": PLACE})
    assert read.output["body"] == "# Installing\n\nRun it twice.\n"
    assert read.output["mark"] == "m1"


async def test_a_write_replaces_only_the_text_it_expects(tmp_path: Path) -> None:
    connector = DirectoryConnector(tmp_path)
    await write(connector)
    with pytest.raises(CallFailed) as refused:
        await write(connector, "# Installing\n\nNew.\n", expected=None, step="second")
    assert refused.value.error.cause is Cause.CONFLICT
    with pytest.raises(CallFailed) as stale:
        await write(connector, "# Installing\n\nNew.\n", expected=digest("other"), step="third")
    assert stale.value.error.cause is Cause.CONFLICT
    await write(connector, "# Installing\n\nNew.\n", expected=digest(BODY), step="fourth")
    read = await connector.call(READ, context("read"), {"place": PLACE})
    assert read.output["body"] == "# Installing\n\nNew.\n"


async def test_a_repeat_with_the_same_key_writes_nothing(tmp_path: Path) -> None:
    connector = DirectoryConnector(tmp_path)
    await write(connector)
    path = tmp_path / "Taktus" / "Administration" / "Installing.md"
    before = path.stat().st_mtime_ns
    repeated = await write(connector)
    assert repeated["replayed"] is True
    assert path.stat().st_mtime_ns == before


async def test_a_place_that_would_leave_the_directory_is_refused(tmp_path: Path) -> None:
    connector = DirectoryConnector(tmp_path / "guides")
    for place in (["..", "x"], ["a/b"], [".hidden"], []):
        with pytest.raises(CallFailed) as refused:
            await connector.call(
                WRITE, context(), {"place": place, "body": BODY, "mark": "m", "expected": None}
            )
        assert refused.value.error.cause is Cause.INVALID
    assert not (tmp_path / "x.md").exists()


async def test_a_missing_page_is_not_found_and_a_file_without_a_mark_has_none(
    tmp_path: Path,
) -> None:
    connector = DirectoryConnector(tmp_path)
    with pytest.raises(CallFailed) as missing:
        await connector.call(READ, context("read"), {"place": PLACE})
    assert missing.value.error.cause is Cause.NOT_FOUND
    (tmp_path / "Notes.md").write_text("Our notes.\n", encoding="utf-8")
    listed = await connector.call(LIST, context("list"), {"place": []})
    assert listed.output == {
        "pages": [{"place": ["Notes"], "digest": digest("Our notes.\n"), "mark": None}]
    }
