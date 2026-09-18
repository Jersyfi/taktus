"""The model port over the chat-completions dialect that most endpoints answer.

One request per completion: `POST {endpoint}/chat/completions` with the model name, the
messages and the output limit, a bearer credential when one is configured, and the answer's
first choice as the text. The dialect is the one a vendor's API, a local model server and most
gateways speak; no vendor's own extensions are used, so that the endpoint is interchangeable.

The credential is a `Secret` read through the configuration port at construction and revealed
only into the request header; it is never logged, never part of an error. An endpoint that
refuses, does not answer, or answers outside the dialect is a `ModelError` naming the endpoint
and the fault.
"""

from __future__ import annotations

from typing import Any

import httpx

from taktus.ports.configuration import Secret
from taktus.ports.model import Completion, Model, ModelError, Prompt

FINISH = {"stop": "stop", "end_turn": "stop", "length": "length", "max_tokens": "length"}


class OpenAiCompatibleModel(Model):
    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        credential: Secret | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._credential = credential
        self._timeout = timeout

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
        return Completion(
            text=text,
            model=str(document.get("model") or self._model),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            finish=FINISH.get(str(choice.get("finish_reason") or ""), "other"),  # type: ignore[arg-type]
        )


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
