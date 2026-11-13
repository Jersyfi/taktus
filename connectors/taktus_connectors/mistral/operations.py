"""How the catalogue of models is asked and its answer read.

The catalogue is `GET /v1/models`: one answer, `data`, without pages, each model with its
`id`, its `created` moment in Unix seconds, its `name`, and `deprecation`, the moment the
provider set for its deprecation, or null while none is set. The requesting identity's key is
sent as a bearer token. The owner, the capabilities, the aliases and the replacement the
provider names are not copied.

`deprecation` becomes `deprecated_at`. The API states no lifecycle stage and no retirement, so
`lifecycle` and `retires_at` are always null; neither is inferred from the deprecation, nor is
the moment compared with the clock. A model with a deprecation set, past or announced, is
`retiring`: it is the provider's notice that the model goes.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 404, 422: the request is refused | `invalid` |
| 401: the key is not admitted | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The provider's own message stays out of `detail`: only its status is reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.mistral.ai"
MODELS_PATH = "/v1/models"
MAX_MODELS = 1000


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    timeout: float = 30.0


async def _get(config: Config, call: Call) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {call.token}"},
        ) as client:
            response = await client.get(MODELS_PATH)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the credential among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the key")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the key may not read the models")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status}")
    if status in (400, 404, 422):
        raise invalid(f"the provider refused the request: {status}")
    if status != 200:
        raise TargetError("unexpected", "none", False, f"the provider answered {status}")
    try:
        answer = json.loads(response.content)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or not isinstance(answer.get("data"), list):
        raise TargetError("unexpected", "none", False, "the answer has no data")
    return answer


def _limit(input: Json) -> int:
    limit = input.get("limit", MAX_MODELS)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_MODELS:
        raise invalid(f"limit must be a whole number from 1 to {MAX_MODELS}")
    return limit


def _created(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")
    raise TargetError("unexpected", "none", False, "a model's creation is not a moment")


def _deprecation(value: Any) -> str | None:
    """The deprecation the provider set, as RFC 3339 UTC; None where none is set."""
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        moment = None
    if moment is None:
        raise TargetError("unexpected", "none", False, "a model's deprecation is not a moment")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _model(entry: Any) -> Json:
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
        raise TargetError("unexpected", "none", False, "a model names no identifier")
    name = entry.get("name")
    return {
        "id": entry["id"],
        "name": name if isinstance(name, str) and name else None,
        "created_at": _created(entry.get("created")),
        "lifecycle": None,
        "deprecated_at": _deprecation(entry.get("deprecation")),
        "retires_at": None,
    }


def retiring(models: list[Json]) -> list[str]:
    """The sorted identifiers of the models with a deprecation set."""
    return sorted(m["id"] for m in models if m["deprecated_at"] is not None)


async def catalogue(config: Config, call: Call, input: Json) -> Outcome:
    """The models the key may use, sorted by identifier. The list API answers in one page."""
    limit = _limit(input)
    answer = await _get(config, call)
    models = sorted((_model(entry) for entry in answer["data"]), key=lambda m: m["id"])
    kept = models[:limit]
    going = retiring(kept)
    output: Json = {
        "models": kept,
        "ids": [m["id"] for m in kept],
        "retiring": going,
        "current": [m["id"] for m in kept if m["id"] not in going],
        "complete": len(kept) == len(models),
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"models.catalogue.list": catalogue}
