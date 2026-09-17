"""Configuration: what an instance is told about itself, by key.

A key is dotted and lowercase — `database.url` — and names one setting. Where the value comes
from is the adapter's business (the environment, today; a file the environment points at, for a
secret). A setting that may carry a secret is read as a `Secret`, which never shows its value
in a log, a message or a traceback; the repository is public and so is every log line a session
might paste (the working rules: no secret value ever enters a file, a log or a message).

A setting that cannot be read as configured — a file that is not there, two sources for one
key — is a `ConfigurationError`: one sentence naming the setting as the operator knows it, so
that the process can refuse to start with that sentence and no stack trace.
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


class ConfigurationError(Exception):
    """A setting cannot be used as configured. `setting` names it the way the operator sees it
    (for the environment adapter: the variable), and the message says what is wrong and what
    to do — never a value."""

    def __init__(self, setting: str, message: str) -> None:
        self.setting = setting
        super().__init__(f"{setting}: {message}")


class Configuration(Protocol):
    def get(self, key: str) -> str | None:
        """The value under `key`, or None when nothing is configured."""
        ...

    def secret(self, key: str) -> Secret | None:
        """The value under `key` as a secret, or None when nothing is configured. Raises
        `ConfigurationError` when something is configured that cannot be read."""
        ...

    def source(self, key: str) -> str | None:
        """Where the value under `key` came from, in words an operator recognises and that
        never include the value — `environment`, `file /run/secrets/x` — or None when nothing
        is configured. For the startup log."""
        ...

    def name(self, key: str) -> str:
        """How the operator writes `key` for this adapter: the variable, for the environment."""
        ...
