"""A tenant's residency rule: where its data may be processed (ADR-0116 §3, UC-11.1).

The rule names a location for the tenant — `own`, its own infrastructure; `eu`, inside the
European Union; or `anywhere` — and may name a narrower one for a class of data and for a
process. A rule for a class or a process is never wider than the tenant's own; where several
apply, the narrowest holds (ADR-0258). A tenant that set no rule holds `anywhere` (NTC-0217).

The rule may also demand the provider's terms of a model its data is sent to: a data-processing
agreement in place, and no training on the data — for all its data, or for a class (ADR-0334).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from taktus.ports.model import PERMITTED, TERMS, Permitted, narrower
from taktus.shared.v1 import Value

DATA_CLASS = re.compile(r"[a-z][a-z0-9_-]*")
PROCESS = re.compile(r"[a-z][a-z0-9-]*")
"""A process's identifier, as a process version names it."""


class ResidencyRule(Value):
    """One tenant's rule, stored under the tenant's own identifier."""

    id: str = Field(min_length=1)
    tenant: str = Field(min_length=1)
    location: Permitted = "anywhere"
    """Where the tenant's data may be processed, unless a class narrows it."""
    classes: dict[str, Permitted] = Field(default_factory=dict)
    """Data class → where data of that class may be processed."""
    processes: dict[str, Permitted] = Field(default_factory=dict)
    """Process → where the data of its runs may be processed (ADR-0258)."""
    terms: tuple[str, ...] = ()
    """The provider's terms a model must declare to be sent any of the tenant's data (ADR-0334)."""
    class_terms: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    """Data class → the terms a model must declare, beside the tenant's, to be sent data of it."""
    configured_at: datetime | None = None
    """When it was configured; None for the shipped default, which nobody configured."""

    @model_validator(mode="after")
    def _sound(self) -> ResidencyRule:
        if self.id != self.tenant:
            raise ValueError(f"a residency rule is stored under its tenant {self.tenant!r}")
        for data_class, location in self.classes.items():
            if DATA_CLASS.fullmatch(data_class) is None:
                raise ValueError(f"{data_class!r} is not a data class: lowercase, digits, - and _")
            if PERMITTED.index(location) > PERMITTED.index(self.location):
                raise ValueError(
                    f"the rule for {data_class!r} ({location}) is wider than the tenant's "
                    f"({self.location}); a class narrows the rule and never widens it"
                )
        for named in (self.terms, *self.class_terms.values()):
            unknown = [term for term in named if term not in TERMS]
            if unknown:
                raise ValueError(f"{', '.join(unknown)} is not a term; one of {', '.join(TERMS)}")
        for data_class in self.class_terms:
            if DATA_CLASS.fullmatch(data_class) is None:
                raise ValueError(f"{data_class!r} is not a data class: lowercase, digits, - and _")
        for process, location in self.processes.items():
            if PROCESS.fullmatch(process) is None:
                raise ValueError(f"{process!r} is not a process: lowercase, digits and -")
            if PERMITTED.index(location) > PERMITTED.index(self.location):
                raise ValueError(
                    f"the rule for the process {process!r} ({location}) is wider than the "
                    f"tenant's ({self.location}); a process narrows the rule and never widens it"
                )
        return self

    def document(self) -> dict[str, Any]:
        """A rule naming no process is written as the previous release wrote it, so that the
        release before reads it (ADR-0093)."""
        written = super().document()
        if not self.processes:
            written.pop("processes", None)
        if not self.terms:
            written.pop("terms", None)
        if not self.class_terms:
            written.pop("class_terms", None)
        return written

    def demanded(self, data_class: str | None) -> frozenset[str]:
        """The terms a model must declare to be sent data of the class: the tenant's, and the
        class's beside them (ADR-0334)."""
        own = self.class_terms.get(data_class, ()) if data_class is not None else ()
        return frozenset((*self.terms, *own))

    def permitted(self, data_class: str | None, process: str | None = None) -> Permitted:
        """Where data of the class may be processed in a run of the process: the narrowest of
        the class's rule, the process's and the tenant's own."""
        held = self.location
        if data_class is not None and data_class in self.classes:
            held = narrower(self.classes[data_class], held)
        if process is not None and process in self.processes:
            held = narrower(self.processes[process], held)
        return held


def shipped_rule(tenant: str) -> ResidencyRule:
    """What a tenant that set no rule holds (NTC-0217): `anywhere`, as before the rule existed."""
    return ResidencyRule(id=tenant, tenant=tenant)
