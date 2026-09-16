"""Plan.json: what is to be achieved, with what, by when, at which autonomy level."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from taktus.shared.v1.autonomy_level import AutonomyLevel
from taktus.shared.v1.step import Step
from taktus.shared.v1.value import Value


class PlanResult(StrEnum):
    RUN = "run"
    PROCESS_VERSION = "process_version"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    COMMISSIONED = "commissioned"
    WITHDRAWN = "withdrawn"


class Commissioned(Value):
    """The recorded act of commissioning: who, when."""

    by: str = Field(min_length=1)
    at: datetime


class Plan(Value):
    id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    autonomy_level: AutonomyLevel
    due: datetime | None = None
    steps: tuple[Step, ...] = Field(min_length=1)
    results_in: PlanResult
    status: PlanStatus
    commissioned: Commissioned | None = None

    @model_validator(mode="after")
    def _commissioning_is_recorded(self) -> Plan:
        if self.status is PlanStatus.COMMISSIONED and self.commissioned is None:
            raise ValueError("a commissioned plan records who commissioned it and when")
        if self.status is not PlanStatus.COMMISSIONED and self.commissioned is not None:
            raise ValueError("only a commissioned plan carries the commissioning record")
        return self
