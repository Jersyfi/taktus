"""The directory connector: a knowledge system made of files, for an organisation that has none.

UC-13.6 says where the guides go when an organisation keeps no wiki: into files it can open
without Taktus. This connector serves the capability `knowledge.pages` over one directory. A page
is one Markdown file; its place is its path, one directory per level and the page's title as
the file's name (`<root>/Taktus/Administration/Installing.md`). Opened in any editor or viewer,
the file shows the page and nothing else.

The mark Taktus keeps beside a page, and the idempotency key of the write that put it there, are
the file's last line: an HTML comment, which a Markdown viewer does not show. Whoever edits the
file can delete it; the page is then one Taktus did not write, and is never overwritten.

Three operations, each counted as one call:

- `knowledge.pages.list`, a read: every page at or below a `place`, each with its `place`,
  `digest` and `mark`, as `pages`;
- `knowledge.pages.read`, a read: one page at a `place` — its `body`, `digest` and `mark`;
  `not_found` where no page is;
- `knowledge.pages.write`, a write with idempotency `marked`: a `body` and a `mark` put at a
  `place`, where the page there has the `expected` digest; it answers the `digest` written.

`digest` is the SHA-256 of the page's text as UTF-8, the mark excluded. A write replaces the page
only where the page's digest is `expected` — `null` when no page may be there — and ends
`conflict` otherwise: whatever changed in between stands. A write whose key the page already
carries, with the same text, is a repeat; it writes nothing and answers `replayed`.

The connector is an adapter like any other: it imports no component, and nothing in the core
knows it serves files. It runs inside the process that uses it, as the loopback connector does,
because a directory is reached through the file system, not over a network.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from taktus.ports.connector import (
    CallContext,
    CallFailed,
    Capabilities,
    Cause,
    Effect,
    EffectReport,
    Error,
    Record,
    Result,
)
from taktus.shared.v1 import Consumption

ADAPTER = "connector.directory"
"""The adapter identifier the ledger records for this connector."""

CAPABILITY = "knowledge.pages"
LIST = f"{CAPABILITY}.list"
READ = f"{CAPABILITY}.read"
WRITE = f"{CAPABILITY}.write"

SUFFIX = ".md"
TRAILER = re.compile(r"^<!-- taktus (\{.*\}) -->$")
FORBIDDEN = re.compile(r"[\x00-\x1f/\\]")

DECLARATION = Capabilities.model_validate(
    {
        "contract": "connector/v1",
        "version": "1",
        "capabilities": [CAPABILITY],
        "operations": [
            {
                "name": LIST,
                "capability": CAPABILITY,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "Every page at or below a place, with the digest of its text and "
                "the mark kept beside it.",
            },
            {
                "name": READ,
                "capability": CAPABILITY,
                "effect": "read",
                "demand": {"quota_units": 1},
                "summary": "One page: its text, the digest of the text, the mark kept beside it.",
            },
            {
                "name": WRITE,
                "capability": CAPABILITY,
                "effect": "write",
                "idempotency": "marked",
                "demand": {"quota_units": 1},
                "summary": "Put a page at a place, with a mark beside it, only where the page "
                "there has the expected digest, or none is there when none is expected. The key "
                "is kept beside the page; a repeat finds it and writes nothing.",
            },
        ],
        "credentials": [],
        "consumption": {"kinds": ["quota"], "unit": "calls", "window_seconds": 3600},
        "permissions": "passthrough",
    }
)


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class DirectoryConnector:
    def __init__(self, root: Path) -> None:
        self._root = root

    async def capabilities(self) -> Capabilities:
        return DECLARATION

    async def call(self, operation: str, context: CallContext, input: Mapping[str, Any]) -> Result:
        try:
            if operation == LIST:
                return _read_result({"pages": self._list(_place(input, allow_root=True))})
            if operation == READ:
                return _read_result(self._read(_place(input)))
            if operation == WRITE:
                return self._write(context, input)
        except CallFailed:
            raise
        except PermissionError as error:
            raise CallFailed(operation, _failure(Cause.FORBIDDEN, str(error))) from error
        except (KeyError, TypeError, ValueError) as error:
            raise CallFailed(
                operation, _failure(Cause.INVALID, f"{type(error).__name__}: {error}")
            ) from error
        except OSError as error:
            raise CallFailed(operation, _failure(Cause.UNAVAILABLE, str(error))) from error
        raise CallFailed(operation, _failure(Cause.NOT_FOUND, f"no operation {operation!r}"))

    def _path(self, place: tuple[str, ...]) -> Path:
        return self._root.joinpath(*place[:-1], place[-1] + SUFFIX)

    def _list(self, place: tuple[str, ...]) -> list[dict[str, Any]]:
        base = self._root.joinpath(*place)
        found: list[dict[str, Any]] = []
        single = self._path(place) if place else None
        if single is not None and single.is_file():
            found.append(self._entry(place, single))
        if base.is_dir():
            for path in sorted(base.rglob("*" + SUFFIX)):
                relative = path.relative_to(self._root).with_suffix("")
                if any(part.startswith(".") for part in relative.parts):
                    continue
                found.append(self._entry(tuple(relative.parts), path))
        return found

    def _entry(self, place: tuple[str, ...], path: Path) -> dict[str, Any]:
        body, kept = _parse(path.read_text(encoding="utf-8"))
        return {"place": list(place), "digest": digest(body), "mark": kept.get("mark")}

    def _read(self, place: tuple[str, ...]) -> dict[str, Any]:
        path = self._path(place)
        if not path.is_file():
            raise CallFailed(READ, _failure(Cause.NOT_FOUND, f"no page at {'/'.join(place)}"))
        body, kept = _parse(path.read_text(encoding="utf-8"))
        return {
            "place": list(place),
            "body": body,
            "digest": digest(body),
            "mark": kept.get("mark"),
        }

    def _write(self, context: CallContext, input: Mapping[str, Any]) -> Result:
        place = _place(input)
        body = input["body"]
        mark = input["mark"]
        expected = input.get("expected")
        if not isinstance(body, str) or not body:
            raise ValueError("`body` is the page's text")
        if not isinstance(mark, str):
            raise ValueError("`mark` is the text kept beside the page")
        if expected is not None and not isinstance(expected, str):
            raise ValueError("`expected` is the digest of the page replaced, or null")
        path = self._path(place)
        written = digest(body)
        if path.is_file():
            held, kept = _parse(path.read_text(encoding="utf-8"))
            if kept.get("key") == context.idempotency_key and digest(held) == written:
                return _write_result(place, written, replayed=True)
            if expected is None:
                raise CallFailed(WRITE, _conflict(f"a page is at {'/'.join(place)} already"))
            if digest(held) != expected:
                raise CallFailed(WRITE, _conflict(f"the page at {'/'.join(place)} changed"))
        elif expected is not None:
            raise CallFailed(WRITE, _conflict(f"no page is at {'/'.join(place)} any more"))
        path.parent.mkdir(parents=True, exist_ok=True)
        trailer = json.dumps(
            {"key": context.idempotency_key, "mark": mark}, sort_keys=True, ensure_ascii=True
        )
        content = body + ("" if body.endswith("\n") else "\n") + f"<!-- taktus {trailer} -->\n"
        _replace(path, content)
        return _write_result(place, written, replayed=False)


def _parse(text: str) -> tuple[str, dict[str, Any]]:
    """The page's text and what is kept beside it, from the file's last line."""
    trimmed = text[:-1] if text.endswith("\n") else text
    cut = trimmed.rfind("\n")
    match = TRAILER.match(trimmed[cut + 1 :])
    if match is None:
        return text, {}
    try:
        kept = json.loads(match.group(1))
    except ValueError:
        return text, {}
    if not isinstance(kept, dict):
        return text, {}
    return trimmed[: cut + 1], kept


def _replace(path: Path, content: str) -> None:
    """Written beside the page and renamed over it, so that a reader never sees half a page."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".taktus-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            file.write(content)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _place(input: Mapping[str, Any], *, allow_root: bool = False) -> tuple[str, ...]:
    place = input["place"]
    if not isinstance(place, list | tuple) or not all(isinstance(p, str) for p in place):
        raise ValueError("`place` is a list of names, one per level")
    if not place and not allow_root:
        raise ValueError("`place` names at least the page")
    for name in place:
        if not name or name.startswith(".") or FORBIDDEN.search(name) or len(name) > 120:
            raise ValueError(f"{name!r} cannot be the name of a level or a page")
    return tuple(place)


def _read_result(output: dict[str, Any]) -> Result:
    return Result(
        output=output, effect=EffectReport(kind=Effect.READ), consumption=Consumption(quota_units=1)
    )


def _write_result(place: tuple[str, ...], written: str, *, replayed: bool) -> Result:
    return Result(
        output={"place": list(place), "digest": written},
        effect=EffectReport(
            kind=Effect.WRITE,
            replayed=replayed,
            records=(Record(kind="page", id="/".join(place)),),
            content_digest=written,
        ),
        consumption=Consumption(quota_units=1),
    )


def _conflict(detail: str) -> Error:
    return _failure(Cause.CONFLICT, detail)


def _failure(cause: Cause, detail: str) -> Error:
    return Error.model_validate(
        {"class": "failure", "cause": cause, "effect": "none", "retryable": False, "detail": detail}
    )
