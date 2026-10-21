"""What every execution adapter needs: the credential values a job names, read once at launch
through the configuration port, the wait until a unit answers health, and a job's token at the
instance's egress gateway (ADR-0115)."""

from __future__ import annotations

import asyncio
import time
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


# --- the instance's egress gateway (ADR-0115) ------------------------------------------------

GATEWAY_KEY = "execution.gateway.key"
"""The configuration key of the key the gateway verifies each job's token with:
`TAKTUS_EXECUTION_GATEWAY_KEY_FILE` (CREDENTIALS.md)."""
PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
TOKEN_SLACK_SECONDS = 60
"""How long a job's token outlives the job's own deadline: the time it takes to end it."""


def gateway_key(configuration: Configuration) -> Secret | None:
    """The configured gateway key, or None when none is configured. A key configured but not
    readable is a refusal in the operator's terms."""
    try:
        return configuration.secret(GATEWAY_KEY)
    except ConfigurationError as error:
        raise ExecutionRefused(str(error)) from None


def job_token(key: bytes, *, job: str, hosts: tuple[str, ...], seconds: int) -> str:
    """The token that admits one job's hosts at the gateway, for `seconds` and a little more."""
    from taktus.adapters.driven.execution.container import egress  # the format's one home

    expires = int(time.time()) + seconds + TOKEN_SLACK_SECONDS
    return egress.mint(key, job=job, hosts=hosts, expires=expires)


def proxy_url(token: str, address: str, port: int) -> str:
    """Where a unit finds the gateway, with its job's token as the password: a value, carried
    as a secret is carried."""
    return f"http://{PROXY_USER}:{token}@{address}:{port}"


PROXY_USER = "taktus"
"""The user a unit presents its token as; the gateway's (`egress.PROXY_USER`)."""
