"""ExactnessClass.json: how wrong a step's result may be."""

from __future__ import annotations

from enum import StrEnum


class ExactnessClass(StrEnum):
    """Limits which methods may produce the result (ADR-0014); carried by result-producing steps
    only (ADR-0018)."""

    EXACT = "exact"
    SOURCED = "sourced"
    TOLERANT = "tolerant"
    FREE = "free"
