"""Writing a store's content to a file and reading it back, off the event loop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


async def write(path: Path, content: Any) -> None:
    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    await asyncio.to_thread(_write)


def read(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
