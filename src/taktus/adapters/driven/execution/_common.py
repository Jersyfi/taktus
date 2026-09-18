"""What every execution adapter needs: the credential values a job names, read once at launch
through the configuration port, and the wait until a unit answers health."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass

import httpx

from taktus.ports.configuration import Configuration, ConfigurationError, Secret
from taktus.ports.execution import ExecutionError, ExecutionRefused
from taktus.ports.worker import CredentialReference

CREDENTIAL_KEY_PREFIX = "credential."


def credential_key(name: str) -> str:
    """The configuration key a credential named in an assignment is supplied under:
    `VCS_TOKEN` → `credential.vcs_token`, which the environment adapter reads as
    `TAKTUS_CREDENTIAL_VCS_TOKEN_FILE` (CREDENTIALS.md)."""
    return CREDENTIAL_KEY_PREFIX + name.lower()


@dataclass(frozen=True)
class ResolvedCredential:
    reference: CredentialReference
    value: Secret


def resolve_credentials(
    configuration: Configuration, references: tuple[CredentialReference, ...]
) -> tuple[ResolvedCredential, ...]:
    """Every credential the job names, with its value — or a refusal naming the first that is
    not configured, in the operator's terms and never with a value."""
    resolved: list[ResolvedCredential] = []
    for reference in references:
        key = credential_key(reference.name)
        try:
            value = configuration.secret(key)
        except ConfigurationError as error:
            raise ExecutionRefused(str(error)) from None
        if value is None:
            raise ExecutionRefused(
                f"credential {reference.name} is not configured: set "
                f"{configuration.name(key)}_FILE to a file that holds its value"
            )
        resolved.append(ResolvedCredential(reference, value))
    return tuple(resolved)


async def wait_until_healthy(
    endpoint: str,
    *,
    within_seconds: float,
    ended: Callable[[], Coroutine[None, None, str | None]],
) -> None:
    """Poll the unit's health until it answers 200, the unit exits (`ended` returns why), or
    the time is up."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + within_seconds
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=1.0)) as client:
        while True:
            if (why := await ended()) is not None:
                raise ExecutionError(f"the execution unit exited before it was ready: {why}")
            try:
                response = await client.get(f"{endpoint}/v1/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if loop.time() >= deadline:
                raise ExecutionError(
                    f"the execution unit at {endpoint} did not answer health within "
                    f"{within_seconds:g}s"
                )
            await asyncio.sleep(0.1)
