"""The conformance suites, as the catalog needs them: run the suite of an adapter's contract
against the endpoint the instance's configuration resolves for it, and say what ran.

The catalog records the conformance half of an adapter's maturity only from a run of this
port, in the same operation (ADR-0044). The port takes an adapter identifier and nothing else:
no report, no verdict, no date. The composition root implements it over the suites under
`taktus.conformance` and the instance's own configuration.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from taktus.components.catalog.domain.model import Configuration, Family
from taktus.shared.v1 import Value


class NotConfigured(LookupError):
    """No configured adapter has the identifier."""


class NotRunnable(Exception):
    """The suite cannot be run against the adapter as configured: the database, which has no
    contract suite, or a connector whose scenario is not configured. Nothing ran, and nothing
    is recorded. The message says what to configure."""


class SuiteRun(Value):
    """What one run of a suite was: against which adapter and configuration, by which contract
    and Taktus version, and the report as the suite wrote it."""

    integration: str = Field(min_length=1)
    family: Family
    contract: str = Field(pattern=r"^[a-z]+/v[0-9]+$")
    taktus_version: str = Field(min_length=1)
    configuration: Configuration
    report: dict[str, Any]
    """The suite's machine-readable report, as `Report.to_dict` writes it."""


class Suites(Protocol):
    async def run(self, integration: str) -> SuiteRun:
        """Run the suite of the adapter's contract against the endpoint the configuration
        resolves for `integration`. Raises `NotConfigured` or `NotRunnable` when nothing can
        run."""
        ...
