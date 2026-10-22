"""What the product finding reads and where it sends (UC-6.12, ADR-0046, ADR-0112).

Three ports. **`Blocks`** is the run's blocked-time accounts, read: every block that ended and
every block still open, as the run records them (ADR-0043). The composition root binds it to the
run's query; this component never imports the run.

**`FindingChannel`** is where findings are sent: the Taktus repository, through a connector, on
an instance whose operator enabled it. It holds every finding it was sent, each with its texts.
The marks in those texts say what it holds (`domain/service/texts.py`), so the instance keeps no
memory of what it sent and a restart sends nothing twice.

**`TenantContent`** is what the tenant holds that must not leave the instance: the values its
runs were given and the values their work states. Every text that leaves for the product is
checked against it first (ADR-0112 §4). The composition root binds it to the run's repository.

**`FindingIntake`** is where an instance sends its product candidates when it has no channel of
its own to the repository: the intake of another instance, which opens or adds to the issue
with its own channel (ADR-0118). What it submits is signed. **`Signatures`** signs and verifies:
the composition root binds it to an adapter of a signature scheme, so that this component
carries no cryptography of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field

from taktus.components.reporting.domain.model import Blocked
from taktus.ports.persistence import Tenant
from taktus.shared.v1 import Value


class Blocks(Protocol):
    async def blocks(self, tenant: Tenant) -> Sequence[Blocked]:
        """Every block of the tenant, ended or open, a rehearsal's left out."""
        ...


class TenantContent(Protocol):
    async def values(self, tenant: Tenant) -> Sequence[str]:
        """Every text and number the tenant's runs were given, and every one their work states,
        as text. The names of operations and capabilities a work calls are not among them: they
        say what the process needs of the product."""
        ...


class Held(Value):
    """One finding a channel holds: where it is, whether it is still open, and its texts — the
    body and every later addition — in order."""

    reference: str = Field(min_length=1)
    open: bool
    texts: tuple[str, ...]


class ChannelIncomplete(Exception):
    """The channel could not read everything it holds. Nothing is sent: a finding sent on an
    incomplete reading could be sent twice."""


class FindingChannel(Protocol):
    @property
    def name(self) -> str:
        """The identifier of the channel's adapter configuration: what the ledger records."""
        ...

    async def held(self, tenant: Tenant) -> Sequence[Held]:
        """Every finding the channel holds, open or closed. Raises `ChannelIncomplete` when it
        cannot read them all."""
        ...

    async def open(self, tenant: Tenant, title: str, body: str, *, key: str) -> str:
        """Open a finding; its reference. The same key again opens nothing new."""
        ...

    async def add(self, tenant: Tenant, reference: str, text: str, *, key: str) -> None:
        """Add a text to an open finding. The same key again adds nothing new."""
        ...


class Signatures(Protocol):
    """A signature scheme with public keys. A private key is derived from a seed the instance
    keeps; a public key and a signature are text."""

    def public(self, seed: bytes) -> str:
        """The public key of the private key the seed gives."""
        ...

    def sign(self, seed: bytes, payload: bytes) -> str: ...

    def verify(self, public: str, payload: bytes, signature: str) -> bool:
        """Whether the signature over the payload was made with the public key's private key;
        False for a key or a signature that cannot be read."""
        ...


class Signed(Value):
    """A submission as it travels: the sender's public key, the payload exactly as it was
    signed, and the signature over it."""

    key: str = Field(min_length=1, max_length=200)
    payload: str = Field(min_length=1, max_length=40000)
    signature: str = Field(min_length=1, max_length=400)


type IntakeAnswer = Literal[
    "opened", "added", "known", "held", "refused", "limited", "forged", "invalid"
]
"""What an intake did with a submission. `opened`, `added`: the issue was opened or added to.
`known`: the repository held it already. `held`: the sender waits for its confirmation.
`refused`: the sender is not admitted. `limited`: over its rate. `forged`: the signature does
not verify. `invalid`: the submission is not one."""


class IntakeUnreachable(Exception):
    """The intake did not answer; the submission is tried again at the next interval."""


@runtime_checkable
class FindingIntake(Protocol):
    @property
    def name(self) -> str:
        """The identifier of the intake's adapter configuration: what the ledger records."""
        ...

    async def submit(self, signed: Signed) -> IntakeAnswer:
        """Hand one signed submission to the intake; what it did. Raises `IntakeUnreachable`
        when it did not answer."""
        ...
