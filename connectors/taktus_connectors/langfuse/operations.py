"""How the evaluation platform is asked and its answers read.

The platform's public HTTP API, under `/api/public/`, with HTTP basic authentication: the
requesting identity's pair `<public key>:<secret key>` as user and password. The requests this
connector makes, as the platform's API reference states them:

- **Copy an evaluation**: `GET /scores/{id}` (the mark); `POST /datasets`; `POST
  /dataset-items` per case; `POST /dataset-run-items` per result; `POST /scores` per score.
- **Read a run's scores**: `GET /datasets/{dataset}/runs/{run}`; `GET /traces/{trace}` per item.
- **Mirror a prompt**: `GET /v2/prompts?name=`; `GET /v2/prompts/{name}?version=` for the
  newest; `POST /v2/prompts`.
- **Read costs**: `GET /traces/{trace}` per trace.

**Marked.** A copy derives every score's identifier from the key's reference, and the platform
keeps a score under the identifier it is given; before acting, the first score is read, and
where it exists the copy is a repeat and writes nothing. A data set's item is identified by the
data set and the case, so that every evaluation of a process scores the same items. A mirrored
prompt version carries the key's reference in its configuration, `taktus.mark`; the newest
versions are read for it before a new one is made.

**Amounts.** A cost is the platform's total cost of a trace, in US dollars, returned as decimal
text exactly as the platform's number reads, never rounded here.

How the platform's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: the body is refused | `invalid` |
| 401: the pair is not admitted | `unauthenticated` |
| 403: the pair may not do this | `forbidden` |
| 404 on a read: no such data set, run or prompt | `not_found` |
| 429, 5xx, a refused connection, a read that timed out | `unavailable`, retryable |
| a write whose answer did not arrive | `unavailable`, effect `unknown`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The platform's own message stays out of `detail`: it can quote what was sent.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx

from taktus_connectors.langfuse.declaration import (
    MAX_ITEMS,
    MAX_LOOKUP,
    MAX_SCORES,
    MAX_TRACES,
)
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://cloud.langfuse.com"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.:/@-]{0,199}$")
TRACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MARK = "taktus-"


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The platform's address; a self-hosted one, its cloud, or a fake's."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def mark(key: str) -> str:
    """The reference a write carries: a digest of the key, not the key itself."""
    return MARK + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def _derived(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def item_id(dataset: str, case: str) -> str:
    return f"item-{_derived(dataset, case)}"


def score_id(reference: str, case: str, name: str) -> str:
    return f"{reference}-{_derived(case, name)}"


def _authorization(token: str) -> str:
    public, colon, secret = token.partition(":")
    if not colon or not public or not secret:
        raise TargetError(
            "unauthenticated", "none", False, "the credential is not `<public key>:<secret key>`"
        )
    return "Basic " + base64.b64encode(token.encode("utf-8")).decode("ascii")


async def _request(
    config: Config,
    call: Call,
    method: str,
    path: str,
    *,
    body: Json | None = None,
    params: Json | None = None,
    acting: bool = False,
    absent: bool = False,
) -> Any:
    """One request. `acting` for a request that writes: a connection lost after it was sent
    leaves its effect unknown. `absent`: a 404 is an answer, None, not an error."""
    call.count()
    effect = "unknown" if acting else "none"
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
        ) as client:
            response = await client.request(
                method,
                f"/api/public{path}",
                json=body,
                params=params,
                headers={"Authorization": _authorization(call.token)},
            )
    except httpx.ConnectError as error:
        raise unavailable(f"the platform could not be reached: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the secret among it.
        raise TargetError(
            "unavailable", effect, True, f"the platform did not answer: {type(error).__name__}"
        ) from error
    status = response.status_code
    if status == 404 and absent:
        return None
    if status in (200, 201):
        try:
            return response.json()
        except ValueError as error:
            raise _unexpected("the platform's answer is not JSON") from error
    if status == 400:
        raise invalid(f"the platform refused the request to {path.split('?')[0]}")
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the platform does not admit the pair")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the pair may not do this")
    if status == 404:
        raise TargetError("not_found", "none", False, "the platform holds no such record")
    if status == 429 or status >= 500:
        raise TargetError("unavailable", effect, True, f"the platform answered {status}")
    raise _unexpected(f"the platform answered {status}")


def _name(value: Any, what: str) -> str:
    if not isinstance(value, str) or NAME.match(value) is None:
        raise invalid(f"{what} must be a name of 1 to 200 letters, digits, spaces or _.:/@-")
    return value


def _trace(value: Any, what: str = "trace") -> str:
    if not isinstance(value, str) or TRACE.match(value) is None:
        raise invalid(f"{what} must be a trace identifier of letters, digits and _.:-")
    return value


def _text(value: Any, what: str, longest: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > longest:
        raise invalid(f"{what} must be text of 1 to {longest} characters")
    return value


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise invalid(f"{what} must be a number")
    return float(value)


def _list(value: Any, what: str, most: int, least: int = 1) -> list[Any]:
    if not isinstance(value, list) or not least <= len(value) <= most:
        raise invalid(f"{what} must be a list of {least} to {most} entries")
    return value


def _write(output: Json, records: list[Json], *, replayed: bool) -> Outcome:
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": records})


# --- evaluations.records ---------------------------------------------------------------------


def _scores(result: Json, where: str) -> list[Json]:
    scores: list[Json] = []
    for n, score in enumerate(_list(result.get("scores"), f"{where}.scores", MAX_SCORES)):
        if not isinstance(score, dict):
            raise invalid(f"{where}.scores[{n}] must be an object")
        entry: Json = {
            "name": _name(score.get("name"), f"{where}.scores[{n}].name"),
            "value": _number(score.get("value"), f"{where}.scores[{n}].value"),
        }
        if score.get("comment") is not None:
            entry["comment"] = _text(score.get("comment"), f"{where}.scores[{n}].comment", 2000)
        scores.append(entry)
    return scores


async def write_records(config: Config, call: Call, input: Json) -> Outcome:
    dataset = _name(input.get("dataset"), "dataset")
    run = _name(input.get("run"), "run")
    description = input.get("description")
    if description is not None:
        description = _text(description, "description", 2000)
    items: list[Json] = []
    for n, item in enumerate(_list(input.get("items"), "items", MAX_ITEMS)):
        if not isinstance(item, dict):
            raise invalid(f"items[{n}] must be an object")
        items.append(
            {
                "id": _name(item.get("id"), f"items[{n}].id"),
                "input": item.get("input"),
                "expected": item.get("expected"),
            }
        )
    known = {i["id"] for i in items}
    results: list[Json] = []
    for n, result in enumerate(_list(input.get("results"), "results", MAX_ITEMS)):
        if not isinstance(result, dict):
            raise invalid(f"results[{n}] must be an object")
        case = _name(result.get("item"), f"results[{n}].item")
        if case not in known:
            raise invalid(f"results[{n}].item names no case of items")
        results.append(
            {
                "item": case,
                "trace": _trace(result.get("trace")),
                "scores": _scores(result, f"results[{n}]"),
            }
        )
    reference = mark(call.key)
    scored = [score_id(reference, r["item"], s["name"]) for r in results for s in r["scores"]]
    records = [{"kind": "evaluation.score", "id": i} for i in scored]
    output = {"dataset": dataset, "run": run, "items": len(items), "scores": len(scored)}
    # Before acting: the first score, under the identifier the key derives.
    if await _request(config, call, "GET", f"/scores/{quote(scored[0], safe='')}", absent=True):
        return _write(output, records, replayed=True)
    await _request(
        config,
        call,
        "POST",
        "/datasets",
        body={"name": dataset, **({"description": description} if description else {})},
        acting=True,
    )
    for item in items:
        await _request(
            config,
            call,
            "POST",
            "/dataset-items",
            body={
                "id": item_id(dataset, item["id"]),
                "datasetName": dataset,
                "input": item["input"],
                "expectedOutput": item["expected"],
                "metadata": {"case": item["id"]},
            },
            acting=True,
        )
    for result in results:
        await _request(
            config,
            call,
            "POST",
            "/dataset-run-items",
            body={
                "runName": run,
                "datasetItemId": item_id(dataset, result["item"]),
                "traceId": result["trace"],
                "metadata": {"taktus.mark": reference},
            },
            acting=True,
        )
        for score in result["scores"]:
            await _request(
                config,
                call,
                "POST",
                "/scores",
                body={
                    "id": score_id(reference, result["item"], score["name"]),
                    "traceId": result["trace"],
                    "name": score["name"],
                    "value": score["value"],
                    "dataType": "NUMERIC",
                    **({"comment": score["comment"]} if "comment" in score else {}),
                },
                acting=True,
            )
    return _write(output, records, replayed=False)


async def read_records(config: Config, call: Call, input: Json) -> Outcome:
    dataset = _name(input.get("dataset"), "dataset")
    run = _name(input.get("run"), "run")
    found = await _request(
        config,
        call,
        "GET",
        f"/datasets/{quote(dataset, safe='')}/runs/{quote(run, safe='')}",
    )
    run_items = found.get("datasetRunItems") if isinstance(found, dict) else None
    if not isinstance(run_items, list):
        raise _unexpected("the run names no items")
    read: list[Json] = []
    for entry in run_items[:MAX_TRACES]:
        if not isinstance(entry, dict) or not isinstance(entry.get("traceId"), str):
            raise _unexpected("an item of the run names no trace")
        trace = await _request(
            config, call, "GET", f"/traces/{quote(entry['traceId'], safe='')}", absent=True
        )
        scores = trace.get("scores") if isinstance(trace, dict) else []
        read.append(
            {
                "item": entry.get("datasetItemId"),
                "trace": entry["traceId"],
                "scores": [
                    {"name": s.get("name"), "value": s.get("value")}
                    for s in scores or []
                    if isinstance(s, dict) and isinstance(s.get("name"), str)
                ],
            }
        )
    return Outcome(
        {
            "dataset": dataset,
            "run": run,
            "items": read,
            "complete": len(run_items) <= MAX_TRACES,
        },
        {"kind": "read"},
    )


# --- prompts.versions ------------------------------------------------------------------------


async def mirror_prompt(config: Config, call: Call, input: Json) -> Outcome:
    name = _name(input.get("name"), "name")
    text = _text(input.get("text"), "text", 100_000)
    source = _text(input.get("source"), "source", 300)
    reference = mark(call.key)
    listed = await _request(config, call, "GET", "/v2/prompts", params={"name": name})
    data = listed.get("data") if isinstance(listed, dict) else None
    if not isinstance(data, list):
        raise _unexpected("the platform's list of prompts is not a list")
    versions: list[int] = []
    for meta in data:
        if isinstance(meta, dict) and meta.get("name") == name:
            versions = [v for v in meta.get("versions") or [] if isinstance(v, int)]
    for held_version in sorted(versions, reverse=True)[:MAX_LOOKUP]:
        held = await _request(
            config,
            call,
            "GET",
            f"/v2/prompts/{quote(name, safe='')}",
            params={"version": held_version},
            absent=True,
        )
        config_of = held.get("config") if isinstance(held, dict) else None
        if isinstance(config_of, dict) and config_of.get("taktus.mark") == reference:
            return _mirrored(name, held_version, replayed=True)
    made = await _request(
        config,
        call,
        "POST",
        "/v2/prompts",
        body={
            "type": "text",
            "name": name,
            "prompt": text,
            "config": {"taktus.mark": reference, "taktus.source": source},
            "labels": [],
            "commitMessage": f"Mirrored from {source}",
        },
        acting=True,
    )
    version = made.get("version") if isinstance(made, dict) else None
    if not isinstance(version, int) or isinstance(version, bool):
        raise TargetError("unexpected", "unknown", True, "the platform answered no version")
    return _mirrored(name, version, replayed=False)


def _mirrored(name: str, version: int, *, replayed: bool) -> Outcome:
    return _write(
        {"name": name, "version": version},
        [{"kind": "prompt.version", "id": f"{name}@{version}"}],
        replayed=replayed,
    )


# --- observability.costs ---------------------------------------------------------------------


def _decimal(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise _unexpected("a cost is not a number")
    try:
        return str(Decimal(str(value)))
    except InvalidOperation as error:
        raise _unexpected("a cost is not a number") from error


async def read_costs(config: Config, call: Call, input: Json) -> Outcome:
    traces = [_trace(t, "traces[]") for t in _list(input.get("traces"), "traces", MAX_TRACES)]
    read: list[Json] = []
    for trace in traces:
        found = await _request(config, call, "GET", f"/traces/{quote(trace, safe='')}", absent=True)
        if found is None:
            read.append({"trace": trace, "absent": True})
            continue
        if not isinstance(found, dict):
            raise _unexpected("a trace is not an object")
        latency = found.get("latency")
        read.append(
            {
                "trace": trace,
                "cost": _decimal(found.get("totalCost")),
                "currency": "USD",
                "latency_seconds": latency
                if isinstance(latency, int | float) and not isinstance(latency, bool)
                else None,
            }
        )
    return Outcome({"traces": read}, {"kind": "read"})


OPERATIONS = {
    "evaluations.records.write": write_records,
    "evaluations.records.read": read_records,
    "prompts.versions.mirror": mirror_prompt,
    "observability.costs.read": read_costs,
}
