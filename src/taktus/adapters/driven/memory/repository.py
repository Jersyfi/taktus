from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from taktus.adapters.driven.memory import _snapshot
from taktus.shared.v1 import Value


class MemoryRepository[T: Value]:
    """A dictionary behind the repository port. `key` says what identifies an item; `model` is
    needed only to read a snapshot."""

    def __init__(
        self, model: type[T], key: Callable[[T], str], snapshot: Path | None = None
    ) -> None:
        self._model = model
        self._snapshot = snapshot
        self._key = key
        self._items: dict[str, T] = {}
        if snapshot is not None:
            for document in _snapshot.read(snapshot) or []:
                item = model.model_validate(document)
                self._items[self._key(item)] = item

    async def get(self, id: str) -> T | None:
        return self._items.get(id)

    async def put(self, item: T) -> None:
        self._items[self._key(item)] = item
        if self._snapshot is not None:
            await _snapshot.write(self._snapshot, [i.document() for i in self._items.values()])

    async def list(self) -> Sequence[T]:
        return list(self._items.values())
