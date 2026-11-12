"""The model port over Vertex AI's `generateContent` (README.md).

One request per completion: `POST {endpoint}/{model}:generateContent`, where the endpoint is a
regional one's publisher path —
`https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google/models`
— with the user text in `contents`, the system text in `systemInstruction` and the output limit
in `generationConfig.maxOutputTokens`. The answer is the first candidate's text parts, joined.

**Who it acts as.** The credential is a service account's key file, as the provider issues it:
JSON with `client_email`, `private_key`, `private_key_id` and `token_uri`. Before a call the
adapter exchanges a signed assertion for an access token at `token_uri` (OAuth 2.0 JWT bearer
grant, RFC 7523), with the scope `https://www.googleapis.com/auth/cloud-platform`, and keeps the
token until a minute before it expires. The key and the token are revealed only into the
assertion and the request header; never logged, never part of an error.

**Where it processes.** A regional endpoint processes in its region: `location_of` reads the
region from the endpoint's host, `eu` for `europe-*`, `elsewhere` for every other region and the
global endpoint (ADR-0248, UC-11.1).

**Before a call** the count is an upper bound, as for the chat-completions adapter: one token
per byte of text plus the overhead per message, never below what the provider bills for text.
**After it** `usageMetadata.promptTokenCount` is every input token, `cachedContentTokenCount`
the part of it read from a cache, and `candidatesTokenCount` plus `thoughtsTokenCount` the
output. A `429` is `ModelAtLimit`.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt

from taktus.adapters.driven.models.openai_compatible.client import EVIDENCE, upper_bound
from taktus.ports.configuration import Secret
from taktus.ports.model import (
    Billing,
    Calculability,
    Completion,
    Model,
    ModelAtLimit,
    ModelError,
    OutputCap,
    Prompt,
    ProviderLimit,
)
from taktus.shared.v1 import PriceKinds

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
FINISH = {"STOP": "stop", "MAX_TOKENS": "length"}
EARLY_SECONDS = 60


def location_of(endpoint: str) -> str:
    """Where a regional endpoint processes: `eu` for a European region, `elsewhere` for any
    other and for the global endpoint."""
    host = urlparse(endpoint).hostname or ""
    region = host.removesuffix("-aiplatform.googleapis.com") if "-aiplatform." in host else ""
    return "eu" if region.startswith("europe-") else "elsewhere"


class VertexModel(Model):
    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        credential: Secret | None = None,
        timeout: float = 120.0,
        billing: Billing = "per_token",
        output_cap: OutputCap = "hard",
        provider_limit: ProviderLimit = "unknown",
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._credential = credential
        self._timeout = timeout
        self._token: tuple[str, float] | None = None
        self._calculability = Calculability(
            input_count="upper_bound",
            output_cap=output_cap,
            usage_kinds=("input", "output", "cache_read"),
            billing=billing,
            provider_limit=provider_limit,
            evidence=EVIDENCE,
        )

    def calculability(self) -> Calculability:
        return self._calculability

    async def count(self, prompt: Prompt) -> int | None:
        return upper_bound(prompt)

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def model_name(self) -> str:
        return self._model

    async def _access_token(self, client: httpx.AsyncClient) -> str | None:
        if self._credential is None:
            return None
        if self._token is not None and self._token[1] > time.time():
            return self._token[0]
        try:
            key = json.loads(self._credential.reveal())
            now = int(time.time())
            assertion = jwt.encode(
                {
                    "iss": key["client_email"],
                    "scope": SCOPE,
                    "aud": key["token_uri"],
                    "iat": now,
                    "exp": now + 3600,
                },
                key["private_key"],
                algorithm="RS256",
                headers={"kid": key.get("private_key_id", "")},
            )
            token_uri = str(key["token_uri"])
        except (ValueError, KeyError, TypeError, jwt.PyJWTError) as error:
            raise ModelError(
                f"the credential for {self._endpoint} is not a service account's key file: "
                f"{type(error).__name__}"
            ) from None
        try:
            response = await client.post(
                token_uri, data={"grant_type": GRANT, "assertion": assertion}
            )
            document = response.json()
            token = str(document["access_token"])
            lifetime = float(document.get("expires_in") or 3600)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ModelError(
                f"no access token for {self._endpoint} from its token endpoint: "
                f"{type(error).__name__}"
            ) from None
        self._token = (token, time.time() + lifetime - EARLY_SECONDS)
        return token

    async def complete(self, prompt: Prompt) -> Completion:
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt.user}]}],
            "generationConfig": {"maxOutputTokens": prompt.max_output_tokens},
        }
        if prompt.system:
            body["systemInstruction"] = {"parts": [{"text": prompt.system}]}
        url = f"{self._endpoint}/{self._model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                token = await self._access_token(client)
                headers = {"Content-Type": "application/json"}
                if token is not None:
                    headers["Authorization"] = f"Bearer {token}"
                response = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise ModelError(
                f"the model endpoint {self._endpoint} did not answer: {type(error).__name__}"
            ) from error
        if response.status_code == 429:
            raise ModelAtLimit(
                f"the model endpoint {self._endpoint} answered 429 for model {self._model!r}: "
                f"the provider's quota is reached: {_message(response)}"
            )
        if response.status_code >= 400:
            raise ModelError(
                f"the model endpoint {self._endpoint} answered {response.status_code} for model "
                f"{self._model!r}: {_message(response)}"
            )
        try:
            document = response.json()
            candidate = document["candidates"][0]
            parts = candidate.get("content", {}).get("parts") or []
            text = "".join(str(p["text"]) for p in parts if "text" in p)
            usage = document.get("usageMetadata") or {}
            tokens_in = int(usage.get("promptTokenCount") or 0)
            cached = min(int(usage.get("cachedContentTokenCount") or 0), tokens_in)
            tokens_out = int(usage.get("candidatesTokenCount") or 0) + int(
                usage.get("thoughtsTokenCount") or 0
            )
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise ModelError(
                f"the model endpoint {self._endpoint} answered outside the generateContent "
                f"shape: {type(error).__name__}"
            ) from error
        kinds: dict[str, int] = {"input": tokens_in - cached, "output": tokens_out}
        if cached:
            kinds["cache_read"] = cached
        return Completion(
            text=text,
            model=str(document.get("modelVersion") or self._model),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            by_kind=PriceKinds.model_validate(kinds),
            finish=FINISH.get(str(candidate.get("finishReason") or ""), "other"),  # type: ignore[arg-type]
        )


def _message(response: httpx.Response) -> str:
    """The endpoint's own words for a refusal, shortened; never the request."""
    try:
        body: Any = response.json()
    except ValueError:
        return f"status {response.status_code}"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:200]
    return f"status {response.status_code}"
