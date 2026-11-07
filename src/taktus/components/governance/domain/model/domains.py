"""A domain an organisation runs through Taktus, and the person who answers for it (ADR-0259,
UC-15.5).

A **domain** is a department or a field of work — finance, support, payroll — that the tenant
instantiates and whose processes Taktus runs. It has exactly one human **owner**: an identity
of the tenant, the addressee of its duties. It has a **jurisdiction**, the country or region
whose law its legally binding acts fall under, as an ISO 3166 code. Its **processes** are the
processes that belong to it, by identifier; a process belongs to one domain at most.

A domain is never instantiated without an owner. When the owner leaves, the domain is kept and
shown without an owner until a new one is named; while it has none, no process of it is raised
in autonomy. The owner is the addressee of the domain, never the subject of a measure of how they
answer for it (principle 14).
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import Field, model_validator

from taktus.shared.v1 import Anchor, Value

DOMAIN_ID = r"^[a-z][a-z0-9-]{0,62}$"
JURISDICTION = r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$"
PROCESS_ID = r"^[a-z][a-z0-9-]*$"


class Domain(Value):
    """One domain of a tenant, stored under its own identifier."""

    id: str = Field(pattern=DOMAIN_ID)
    tenant: str = Field(min_length=1)
    name: str = Field(min_length=1)
    owner: str | None = Field(default=None, min_length=1)
    """The identity that owns the domain; None once the owner left and until one is named."""
    jurisdiction: str = Field(pattern=JURISDICTION)
    processes: tuple[str, ...] = ()
    created_at: datetime

    @model_validator(mode="after")
    def _each_process_once(self) -> Domain:
        for process in self.processes:
            if re.fullmatch(PROCESS_ID, process) is None:
                raise ValueError(f"{process!r} is not a process identifier")
        if len(set(self.processes)) != len(self.processes):
            raise ValueError(f"the domain {self.id!r} names a process twice")
        return self


class DomainView(Value):
    """A domain as its owner and the administrator see it (UC-15.5 §2)."""

    domain: str
    name: str
    owner: str | None
    """None: the domain is shown without an owner, and nothing in it is raised."""
    jurisdiction: str
    processes: tuple[str, ...]
    legal: tuple[Anchor, ...]
    """The legal anchors in force for the domain: the tenant's that apply to its scope."""
    takeover: dict[str, bool]
    """Per process, whether a person passed the trial of its takeover instructions."""
    removal: dict[str, bool]
    """Per process, whether the removal test of every adapter serving it found nothing broken."""

    @property
    def runs_without_taktus(self) -> bool:
        """Shown as able to run without Taktus only where both tests passed for every process
        of the domain; a domain without processes is not."""
        return bool(self.processes) and all(
            self.takeover.get(p, False) and self.removal.get(p, False) for p in self.processes
        )
