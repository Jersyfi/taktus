"""A minimal Server-Sent Events reader, as the specification defines the wire format.

One message is a block of `field: value` lines ended by a blank line. The suite needs three
fields: `id` (carries seq), `event` (carries type) and `data` (one line of JSON). Comment lines
start with a colon. `retry` is read and ignored.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class Message:
    id: str | None = None
    event: str | None = None
    data: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.data)


async def messages(lines: AsyncIterator[str]) -> AsyncIterator[Message]:
    current = Message()
    async for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if current.data or current.id is not None or current.event is not None:
                yield current
            current = Message()
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if name == "id":
            current.id = value
        elif name == "event":
            current.event = value
        elif name == "data":
            current.data.append(value)
    if current.data or current.id is not None or current.event is not None:
        yield current
