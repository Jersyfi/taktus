"""Administration: which platforms the credentials an instance maps can change (ADR-0052).

An instance never runs on infrastructure it administers itself (ADR-0025 §1). To check that
while planning, the instance is told the platform it runs on, and the operator declares beside
every credential the platforms that credential administers. Nothing here asks a platform
anything: the declarations are configuration, and the check is as true as they are.

`Administration` is that configuration as one value. `refusal` says, for a step and the
credential names it uses, why it may not run here — a credential declared to administer this
instance's platform, or one declared about nothing — or None when it may. With no platform
named, nothing is checked; the composition root says so at start.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import Field

from taktus.shared.v1 import Value

NONE = "none"
"""The declaration of a credential that administers no platform."""


class Administration(Value):
    platform: str | None = None
    """The identifier of the platform this instance runs on (`TAKTUS_PLATFORM`), or None when
    the operator named none — then nothing is checked."""
    declared: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    """Per credential name, the platforms it administers (`TAKTUS_CREDENTIAL_<NAME>_ADMINISTERS`);
    an empty tuple is the declaration `none`. A name missing here is undeclared."""

    @property
    def checked(self) -> bool:
        return self.platform is not None

    def refusal(self, step: str, names: Iterable[str]) -> str | None:
        """Why the step may not use these credentials on this instance, or None."""
        if self.platform is None:
            return None
        findings: list[str] = []
        for name in dict.fromkeys(names):
            platforms = self.declared.get(name)
            if platforms is None:
                findings.append(
                    f"credential {name!r} is undeclared: nothing says which platforms it "
                    f"administers (TAKTUS_CREDENTIAL_{name.upper()}_ADMINISTERS)"
                )
            elif self.platform in platforms:
                findings.append(
                    f"credential {name!r} administers {self.platform!r}, the platform this "
                    "instance runs on"
                )
        if not findings:
            return None
        return (
            f"step {step!r} may not run here: "
            + "; ".join(findings)
            + ". No instance runs on infrastructure it administers itself (ADR-0025, ADR-0052)"
        )
