"""Whether a text carries a secret value the instance holds (no message carries one).

Every text this component sends — a report, a reflection, a task — is checked before it leaves.
One that carries a secret is not sent. The composition root answers from the values the
instance itself was configured with; the component never holds one.
"""

from __future__ import annotations

from typing import Protocol


class SecretValues(Protocol):
    def carried_by(self, text: str) -> bool: ...
