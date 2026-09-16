from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class SystemIdentifiers:
    """Prefix, underscore, 20 characters of randomness. Unique for any practical purpose;
    ordering by time is not promised and not relied on."""

    def new(self, prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(10)}"


class SystemRandomness:
    def token(self, length: int) -> str:
        return secrets.token_hex(length)
