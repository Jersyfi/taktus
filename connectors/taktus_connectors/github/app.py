"""Taktus's own app on the service: an installation token minted from the app's private key.

An *app* is an identity on the service that is not a person (DEC-0058, ADR-0033). It is installed
on chosen repositories with chosen permissions. To act, it signs a short-lived JSON Web Token
(a *JWT*: a signed statement "I am app N, until time T") with its private key, and exchanges that
for an *installation token*: a token that lives one hour and carries exactly the permissions of
the installation. The connector acts with the installation token like with any other token.

What this module promises, and how:

- **Minted for use, never stored.** The token is held in this process's memory and nowhere else;
  it is never written to a file, a result, an error or the log. The private key is read from its
  file at each minting and dropped after signing, so that a replaced key takes effect at once.
- **Refreshed before it expires.** A token with less than `REFRESH_MARGIN` left is replaced
  before it is used, so that no call starts with a token that may expire under it.
- **Narrowed to the one repository.** The exchange asks for the connector's repository alone,
  whatever else the installation covers.
- **A refusal says why.** A key the service does not accept, an app that is not installed on the
  repository, a suspended installation: each ends the call `unauthenticated`, with no effect and
  not retryable, and the detail names which of them it was.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import jwt

from taktus.adapters.driven.connectors.github.api import Api, TargetError

APP_ID_VARIABLE = "TAKTUS_REPOSITORY_APP_ID"
"""The app's identifier, configuration key `repository.app_id`. Not a secret; it names the app
and grants nothing without the key."""
APP_KEY_VARIABLE = "TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE"
"""The file that holds the app's private key, credential `repository_app_key` (CREDENTIALS.md)."""

JWT_LIFETIME = 540
"""Seconds a signed statement is valid. The service accepts at most ten minutes."""
CLOCK_SKEW = 60
"""Seconds the statement is dated back, so that a clock slightly ahead of the service's still
produces a statement the service accepts."""
REFRESH_MARGIN = 300
"""Seconds before its expiry at which a held token is replaced instead of used."""


@dataclass(frozen=True)
class AppConfig:
    """Which app, and where its key is. Neither is the key itself."""

    app_id: str
    key_file: Path

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> AppConfig | None:
        """The app named by the environment, or None for the token mode. One of the two
        variables without the other is a configuration fault, not a mode."""
        env = os.environ if environ is None else environ
        app_id = env.get(APP_ID_VARIABLE, "").strip()
        key_file = env.get(APP_KEY_VARIABLE, "").strip()
        if not app_id and not key_file:
            return None
        if not app_id or not key_file:
            missing = APP_KEY_VARIABLE if app_id else APP_ID_VARIABLE
            raise ValueError(
                f"the app mode needs {APP_ID_VARIABLE} and {APP_KEY_VARIABLE}; {missing} is not set"
            )
        return cls(app_id, Path(key_file))


def refused(detail: str, status: int = 0) -> TargetError:
    return TargetError("unauthenticated", "none", False, detail, status)


class AppTokens:
    """One installation token for one repository, minted when needed and held in memory."""

    def __init__(
        self,
        config: AppConfig,
        target: str,
        repository: str,
        *,
        timeout: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.target = target
        self.repository = repository
        self.timeout = timeout
        self.clock = clock
        self._token: str | None = None
        self._expires = 0.0
        self._installation: int | None = None
        self._lock = asyncio.Lock()
        self.spent = 0
        """Requests the last minting made, also when it failed: the call that needed the token
        counts them as its own consumption."""

    async def token(self) -> tuple[str, int]:
        """A token valid for at least `REFRESH_MARGIN` seconds, and how many requests it took
        to get it: none when the held one is still good."""
        async with self._lock:
            if self._token is not None and self.clock() < self._expires - REFRESH_MARGIN:
                return self._token, 0
            self._token = None
            self.spent = 0
            return await self._mint()

    def forget(self) -> None:
        """The service refused the held token: it is dropped, and the next call mints anew."""
        self._token = None
        self._installation = None

    async def _mint(self) -> tuple[str, int]:
        statement = self._statement()
        api = Api(self.target, self.repository, statement, timeout=self.timeout)
        try:
            if self._installation is None:
                self._installation = await self._installation_of(api)
            token, expires = await self._exchange(api, self._installation)
        finally:
            self.spent = api.requests
            await api.close()
        self._token, self._expires = token, expires
        return token, api.requests

    def _statement(self) -> str:
        try:
            key = self.config.key_file.read_text(encoding="utf-8")
        except OSError:
            raise refused(
                f"the app's private key cannot be read from the file {APP_KEY_VARIABLE} names"
            ) from None
        now = int(time.time())  # the service checks the statement against its own clock
        claims = {"iat": now - CLOCK_SKEW, "exp": now + JWT_LIFETIME, "iss": self.config.app_id}
        try:
            return jwt.encode(claims, key, algorithm="RS256")
        except (ValueError, TypeError, jwt.PyJWTError):
            raise refused(
                f"the file {APP_KEY_VARIABLE} names does not hold a usable RSA private key"
            ) from None
        finally:
            del key

    async def _installation_of(self, api: Api) -> int:
        try:
            found = await api.get(api.repo("installation"))
        except TargetError as error:
            raise self._explain(error, "looking up the app's installation") from None
        if not isinstance(found, dict) or not isinstance(found.get("id"), int):
            raise TargetError(
                "unavailable", "none", True, "the service named no installation of the app"
            )
        return int(found["id"])

    async def _exchange(self, api: Api, installation: int) -> tuple[str, float]:
        name = self.repository.split("/", 1)[1]
        try:
            issued = await api.post(
                f"/app/installations/{installation}/access_tokens", {"repositories": [name]}
            )
        except TargetError as error:
            if error.status == 404:
                self._installation = None
            raise self._explain(error, "minting an installation token") from None
        token = issued.get("token") if isinstance(issued, dict) else None
        expires_at = issued.get("expires_at") if isinstance(issued, dict) else None
        if not isinstance(token, str) or not token or not isinstance(expires_at, str):
            raise TargetError(
                "unavailable", "none", True, "the service answered the exchange without a token"
            )
        try:
            expires = datetime.fromisoformat(expires_at).timestamp()
        except ValueError:
            raise TargetError(
                "unavailable", "none", True, "the service gave the token an unreadable expiry"
            ) from None
        return token, expires

    def _explain(self, error: TargetError, doing: str) -> TargetError:
        """A refusal while minting, as the reason a person can act on. A fault of the service or
        of the connection keeps its own cause: it is not the app's."""
        if error.status == 401:
            return refused(
                f"{doing}: the service did not accept the app's signed statement — the key was "
                "replaced or deleted, or the app identifier is not the key's app",
                401,
            )
        if error.status == 404:
            return refused(
                f"{doing}: the app is not installed on {self.repository}, or its installation "
                "was removed",
                404,
            )
        if error.status == 403 and error.cause == "forbidden":
            reason = error.detail.split(": ", 1)[-1]
            return refused(f"{doing}: the installation refused a token — {reason}", 403)
        return error
