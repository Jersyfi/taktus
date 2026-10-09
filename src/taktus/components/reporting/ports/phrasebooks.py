"""The phrasebooks Taktus ships, by language (ADR-0045).

A tenant may write its own phrasebook into its configuration, or name a language and take the
one Taktus ships for it. Where the shipped ones live is the composition root's: the core names
no language.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class Phrasebooks(Protocol):
    def shipped(self, language: str) -> Mapping[str, Any] | None:
        """The shipped phrasebook for the language tag, or None when Taktus ships none."""
        ...
