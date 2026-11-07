"""The department of a person who answered a wait, seen from the run (ADR-0283 §4).

The blocked-time accounts group the waits on people by department as well as by role. A
department is where the person who answered sits in the tenant's structure, which the identity
component keeps. The composition root answers from it, because components never import each
other. The person is asked about only to be counted and placed; neither is ever kept.
"""

from __future__ import annotations

from typing import Protocol

from taktus.ports.persistence import Tenant


class Departments(Protocol):
    async def department(self, tenant: Tenant, identity: str) -> str | None:
        """The department the identity sits in, or None where it sits in none or is not
        known."""
        ...
