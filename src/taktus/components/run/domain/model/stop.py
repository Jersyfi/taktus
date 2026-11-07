"""A stop of a tenant's runs, scoped to an adapter, a process or the whole tenant, as the tenant
keeps it (ADR-0138, ADR-0256, UC-7.2).

A **stop of an adapter** halts every step that adapter serves, in every run of the tenant, at
the step's boundary, and nothing else. A **stop of a process** halts every run of the process at
its next boundary, and a **stop of the tenant** every run of the tenant; a stop of the instance
is a stop of each tenant it serves (ADR-0256 §1). A stop of one run is the run's own
(`RunEngine.request_stop`) and is not kept here.

A person's stop asks for no reason. A rule's stop names the rule that fired and the incident
whose facts it read (ADR-0023, ADR-0256 §3). A stop is *holding* from the moment it is
requested, *confirmed* once no run it covers is still inside a step, and *lifted* when a person
lifts it. A lifted stop resumes nothing: each run it stopped is resumed by a person, as every
stopped run is.

The confirmation names the runs the stop halted. It is computed from the runs themselves — a
run halted with cause `stop` under the stop's scope, at or after the request — so that no
runner writes the stop's record.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from taktus.shared.v1 import Value


class StopState(StrEnum):
    HOLDING = "holding"
    """Requested: no step is handed on under its scope, and the steps inside stop at their
    boundary. Not yet every affected run has reached it."""
    CONFIRMED = "confirmed"
    """Every affected run reached its boundary; the confirmation was recorded. The stop still
    holds: no step is handed on under its scope."""
    LIFTED = "lifted"
    """A person lifted it: steps are handed on again."""


class StopScope(StrEnum):
    ADAPTER = "adapter"
    """Every step one adapter serves (ADR-0138)."""
    PROCESS = "process"
    """Every run of one process (ADR-0256)."""
    TENANT = "tenant"
    """Every run of the tenant (ADR-0256)."""


HELD = (StopState.HOLDING, StopState.CONFIRMED)
"""The states in which a stop keeps steps from being handed on."""


class AdapterStop(Value):
    """One stop of a tenant: of one adapter, one process, or the tenant. The name is the one
    ADR-0138 gave it; the scope says what it holds."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    scope: StopScope = StopScope.ADAPTER
    adapter: str | None = Field(default=None, min_length=1)
    """The adapter as the pool names it — `worker.coding`, never a product — for a stop of an
    adapter; None for any other."""
    process: str | None = Field(default=None, min_length=1)
    """The process's identifier, for a stop of a process; None for any other."""
    requested_by: str = Field(min_length=1)
    """The identity that requested it, to whom the confirmation is addressed; for a rule's
    stop, `rule:` and the rules that fired."""
    rule: str | None = Field(default=None, min_length=1)
    """The rules that fired, for a stop a rule requested (ADR-0023); None for a person's."""
    incident: str | None = Field(default=None, min_length=1)
    """The incident that carries the facts the rule read and its narrative (UC-6.8)."""
    requested_at: datetime
    created_at: datetime
    state: StopState = StopState.HOLDING
    confirmed_at: datetime | None = None
    stopped: tuple[str, ...] = ()
    """The runs it halted, as the confirmation names them; empty before it and for a stop that
    found no run."""
    lifted_by: str | None = Field(default=None, min_length=1)
    lifted_at: datetime | None = None

    @model_validator(mode="after")
    def _names_its_scope(self) -> AdapterStop:
        if (self.scope is StopScope.ADAPTER) != (self.adapter is not None):
            raise ValueError("a stop names an adapter exactly when it is a stop of an adapter")
        if (self.scope is StopScope.PROCESS) != (self.process is not None):
            raise ValueError("a stop names a process exactly when it is a stop of a process")
        if (self.rule is None) != (self.incident is None):
            raise ValueError("a rule's stop names the rule and the incident that carries it")
        return self

    def document(self) -> dict[str, Any]:
        """A stop of an adapter is written as the previous release wrote it, without its scope,
        so that the release before reads it (ADR-0093)."""
        written = super().document()
        if self.scope is StopScope.ADAPTER:
            written.pop("scope", None)
        return written

    @property
    def held(self) -> bool:
        return self.state in HELD

    @property
    def target(self) -> str:
        """What it stops, as a reader names it: the adapter, the process, or the tenant."""
        return self.adapter or self.process or self.tenant

    def covers(self, process: str) -> bool:
        """Whether a held stop halts a run of the process at its next boundary, whatever
        adapter its step is on: a stop of the process or of the tenant."""
        if not self.held:
            return False
        return self.scope is StopScope.TENANT or (
            self.scope is StopScope.PROCESS and self.process == process
        )


def process_of(process_version: str) -> str:
    """The process a version reference names: `billing@3` is a version of `billing`."""
    return process_version.rpartition("@")[0] or process_version
