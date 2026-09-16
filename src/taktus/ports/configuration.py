"""Configuration: what an instance is told about itself, by key.

A key is dotted and lowercase — `database.url` — and names one setting. Where the value comes
from is the adapter's business (the environment, today). A setting that may carry a secret is
read as a `Secret`, which never shows its value in a log, a message or a traceback; the
repository is public and so is every log line a session might paste (CLAUDE.md §9).
"""

from __future__ import annotations

import hmac
from typing import Protocol


class Secret:
    """A value that is never shown. `reveal()` is the one way to the string, and the call
    site that reveals it is the one place to look when a value leaks."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        return hmac.compare_digest(self._value.encode(), other._value.encode())

    def __hash__(self) -> int:
        return hash(self._value)


class Configuration(Protocol):
    def get(self, key: str) -> str | None:
        """The value under `key`, or None when nothing is configured."""
        ...

    def secret(self, key: str) -> Secret | None:
        """The value under `key` as a secret, or None when nothing is configured."""
        ...
