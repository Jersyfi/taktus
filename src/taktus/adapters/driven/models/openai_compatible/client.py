"""The model port over the chat-completions dialect that most endpoints answer.

One request per completion: `POST {endpoint}/chat/completions` with the model name, the
messages and the output limit, a bearer credential when one is configured, and the answer's
first choice as the text. The dialect is the one a vendor's API, a local model server and most
gateways speak; no vendor's own extensions are used, so that the endpoint is interchangeable.

The credential is a `Secret` read through the configuration port at construction and revealed
only into the request header; it is never logged, never part of an error. An endpoint that
refuses, does not answer, or answers outside the dialect is a `ModelError` naming the endpoint
and the fault.

**What it can say before a call.** The dialect has no endpoint that counts tokens. The adapter
therefore declares its count an **upper bound** and computes it: a tokenizer that works on
bytes emits at most one token per byte of text, so the UTF-8 length of every message plus a
fixed overhead per message is never below what the provider bills for text. It over-reserves,
and it is safe; `contracts/model/v1` check M-02 holds a live endpoint to it. Whether the output
limit is hard, and how the provider bills, the dialect does not say either: the operator
declares both for the configured endpoint (`TAKTUS_MODEL_OUTPUT_CAP`, `TAKTUS_MODEL_BILLING`),
and the defaults are the cautious ones — a soft cap, billing per token. The evidence for what
providers permit is `docs/research/2026-09-30-what-providers-allow.md`.

**After it.** `usage.prompt_tokens` is every input token. Where the endpoint reports how many
were read from a cache or written to one, the completion splits them by price kind. An endpoint
reports them in one of two shapes, and the adapter reads both: nested
(`prompt_tokens_details.cached_tokens`, `prompt_tokens_details.cache_write_tokens`) and at the
top level of the usage (`cache_read_input_tokens`, `cache_creation_input_tokens`). Where both
shapes report a kind, they report the same tokens, and the larger count is booked once. Where
the cached tokens exceed `prompt_tokens`, the total cannot include them: it is then the uncached
input alone, and the input is the sum. Which kinds the endpoint reports the operator declares
(`TAKTUS_MODEL_USAGE_KINDS`); conformance check M-04 holds the endpoint to it.

**At the provider's limit.** A `429` is `ModelAtLimit`. A `Retry-After` header on it, in
seconds or as an HTTP date, is passed on as the delay the provider asked for (ADR-0043).
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from taktus.ports.configuration import Secret
from taktus.ports.model import (
    Billing,
    Calculability,
    Completion,
    Model,
    ModelAtLimit,
    ModelError,
    OutputCap,
    PriceKindName,
    Prompt,
    ProviderLimit,
)
from taktus.shared.v1 import PriceKinds

FINISH = {"stop": "stop", "end_turn": "stop", "length": "length", "max_tokens": "length"}

MESSAGE_OVERHEAD = 16
"""Tokens a chat template adds around one message — role markers, separators — at most. Every
template in the research of 2026-09-30 stays below it; a template that does not would show as
a failed M-02 against its endpoint."""
REQUEST_OVERHEAD = 16
"""Tokens a chat template adds once per request — a beginning marker, the assistant's cue."""
EVIDENCE = "docs/research/2026-09-30-what-providers-allow.md"


def upper_bound(prompt: Prompt) -> int:
    """At most as many input tokens as the provider bills for this prompt's text: one per byte
    of every message, plus the template's overhead."""
    messages = [text for text in (prompt.system, prompt.user) if text]
    return REQUEST_OVERHEAD + sum(len(text.encode("utf-8")) + MESSAGE_OVERHEAD for text in messages)


class OpenAiCompatibleModel(Model):
    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        credential: Secret | None = None,
        timeout: float = 120.0,
        billing: Billing = "per_token",
        output_cap: OutputCap = "soft",
        provider_limit: ProviderLimit = "unknown",
        usage_kinds: tuple[PriceKindName, ...] = ("input", "output"),
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._credential = credential
        self._timeout = timeout
        self._calculability = Calculability(
            input_count="upper_bound",
            output_cap=output_cap,
            usage_kinds=usage_kinds,
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

    async def complete(self, prompt: Prompt) -> Completion:
        messages: list[dict[str, str]] = []
        if prompt.system:
            messages.append({"role": "system", "content": prompt.system})
        messages.append({"role": "user", "content": prompt.user})
        body = {
            "model": self._model,
            "messages": messages,
            "max_tokens": prompt.max_output_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self._credential is not None:
            headers["Authorization"] = f"Bearer {self._credential.reveal()}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._endpoint}/chat/completions", json=body, headers=headers
                )
        except httpx.HTTPError as error:
            raise ModelError(
                f"the model endpoint {self._endpoint} did not answer: {type(error).__name__}"
            ) from error
        if response.status_code == 429:
            retry_after = _retry_after(response.headers.get("Retry-After"))
            asked = "" if retry_after is None else f" (Retry-After {retry_after:.0f}s)"
            raise ModelAtLimit(
                f"the model endpoint {self._endpoint} answered 429 for model {self._model!r}: "
                f"the provider's rate limit is reached{asked}: {_message(response)}",
                retry_after_seconds=retry_after,
            )
        if response.status_code >= 400:
            raise ModelError(
                f"the model endpoint {self._endpoint} answered {response.status_code} for model "
                f"{self._model!r}: {_message(response)}"
            )
        try:
            document = response.json()
            choice = document["choices"][0]
            text = choice["message"]["content"]
            usage = document.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ModelError(
                f"the model endpoint {self._endpoint} answered outside the chat-completions "
                f"shape: {type(error).__name__}"
            ) from error
        if not isinstance(text, str):
            raise ModelError(f"the model endpoint {self._endpoint} answered without text")
        if not isinstance(usage, dict):
            raise ModelError(
                f"the model endpoint {self._endpoint} answered outside the chat-completions "
                "shape: the usage is not an object"
            )
        tokens_in, by_kind = _by_kind(usage)
        tokens_out = int(usage.get("completion_tokens") or 0)
        return Completion(
            text=text,
            model=str(document.get("model") or self._model),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            by_kind=PriceKinds.model_validate({**by_kind, "output": tokens_out}),
            finish=FINISH.get(str(choice.get("finish_reason") or ""), "other"),  # type: ignore[arg-type]
        )


def _by_kind(usage: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """Every input token, and the input split by price kind as far as the endpoint reports the
    split: read from a cache and written to one, in either shape, the rest uncached. A kind the
    endpoint does not report, or reports as zero, is left out. `contracts/model/v1` §5 states
    the rule; `tests/conformance` holds this to the conformance suite's reading of it."""
    prompt = int(usage.get("prompt_tokens") or 0)
    details = usage.get("prompt_tokens_details")
    nested = details if isinstance(details, dict) else {}
    read = max(_tokens(nested, "cached_tokens"), _tokens(usage, "cache_read_input_tokens"))
    written = max(
        _tokens(nested, "cache_write_tokens"), _tokens(usage, "cache_creation_input_tokens")
    )
    if read + written > prompt:
        # The total cannot hold the cached tokens: it is the uncached input alone.
        tokens_in, uncached = prompt + read + written, prompt
    else:
        tokens_in, uncached = prompt, prompt - read - written
    kinds = {"input": uncached}
    if read:
        kinds["cache_read"] = read
    if written:
        kinds["cache_write"] = written
    return tokens_in, kinds


def _tokens(where: dict[str, Any], name: str) -> int:
    value = where.get(name)
    return value if isinstance(value, int) and value > 0 else 0


def _retry_after(value: str | None) -> float | None:
    """The delay a `Retry-After` header asks for, in seconds: a number of seconds, or the time
    until an HTTP date, never below zero. None when there is no header or it says neither."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _message(response: httpx.Response) -> str:
    """The endpoint's own words for a refusal, shortened: never a request body, which could
    carry a credential."""
    try:
        body: Any = response.json()
    except ValueError:
        return f"status {response.status_code}"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:200]
        if body.get("message"):
            return str(body["message"])[:200]
    return f"status {response.status_code}"
