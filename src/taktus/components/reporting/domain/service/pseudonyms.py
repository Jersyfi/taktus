"""The references a finding carries outside its instance (ADR-0112 §2, §3).

A run's identifier and a step's identifier are chosen on the instance. A trigger derives a run's
identifier, and a process names its steps. Either can say something about the tenant. So no
finding carries them as they are. It carries a *pseudonym* of each instead: an HMAC-SHA-256 of
the identifier, under a key drawn at random for the tenant on its instance and never sent.

The same run gives the same pseudonym every time, so occurrences can still be told apart and
the same step recognised. Nobody without the key can compute a pseudonym from a guessed
identifier. The instance holds the key, so its operator can say which run a pseudonym stands for
(`taktusctl findings`).

The *source* is derived from the same key: the identifier of the sender, one tenant of one
instance. It is random, so it names no person, no operator and no tenant.

Pure: a key in, references out.
"""

from __future__ import annotations

import hashlib
import hmac

from taktus.components.reporting.domain.model.finding import Finding, Occurrence

KEY_BYTES = 32
"""The length of a tenant's key, drawn from the randomness port."""


class Pseudonyms:
    """The references of one sender, under its key."""

    def __init__(self, key: bytes) -> None:
        if len(key) < KEY_BYTES:
            raise ValueError(f"a sender's key has at least {KEY_BYTES} bytes")
        self._key = key

    def _digest(self, purpose: str, value: str) -> str:
        message = f"{purpose}\x00{value}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    @property
    def source(self) -> str:
        """The sender's identifier: `src_` and twenty hex digits."""
        return "src_" + self._digest("source", "")[:20]

    def run(self, run_id: str) -> str:
        return "r-" + self._digest("run", run_id)[:16]

    def step(self, step_id: str) -> str:
        return "s-" + self._digest("step", step_id)[:12]

    def occurrence(self, occurrence: Occurrence) -> Occurrence:
        """The occurrence as it leaves: its run and its step by pseudonym, and its sender."""
        return occurrence.model_copy(
            update={
                "run_id": self.run(occurrence.run_id),
                "step_id": self.step(occurrence.step_id),
                "source": self.source,
            }
        )

    def finding(self, finding: Finding) -> Finding:
        return finding.model_copy(
            update={"occurrences": tuple(self.occurrence(o) for o in finding.occurrences)}
        )
