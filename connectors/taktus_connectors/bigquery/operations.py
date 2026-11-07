"""How the warehouse is asked a query, and its answer read.

A query is `POST /bigquery/v2/projects/<project>/queries` (jobs.query) with `query`,
`useLegacySql: false`, `defaultDataset` — the configured dataset, so that an unqualified table
name resolves into the copy without personal fields — `maxResults`, `timeoutMs`, and named
`queryParameters`, with the service account's access token as a bearer token (`auth.py`). An
answer with `jobComplete: false` is followed by
`GET /bigquery/v2/projects/<project>/queries/<jobId>` (jobs.getQueryResults) until it is
complete or the connector's timeout passes; a `pageToken` names the next page. Rows come as
`{"f": [{"v": ...}]}` in the order of `schema.fields`.

**Read only, twice.** The statement must begin with SELECT or WITH, after comments and
whitespace, or it is refused unsent (`invalid`). Then the same request runs as a dry run
(`dryRun: true`): the warehouse validates it and answers `statementType` without running it.
Anything but `SELECT` — a script, a DML or DDL statement — is refused (`forbidden`), and the
query never runs. What the service account may read beyond the dataset is bounded by its
rights in the project, not by the connector (`README.md`).

How the API's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400: a query the warehouse refuses (`invalidQuery`) | `invalid` |
| 404: no such project, dataset or table | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the service account may not run jobs or read the table | `forbidden` |
| 429, 5xx, no connection, no answer in time, a job not done in time | `unavailable`, retryable |
| any other status, a body that is not the API's | `unexpected` |

The API's own `message` stays out of the error's `detail`: it can quote the query.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.bigquery.auth import access_token, token_endpoint
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://bigquery.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/bigquery.readonly"
LIMIT = 1000
MAX_LIMIT = 10000
MAX_QUERY = 100_000
MAX_PAGES = 10
WAIT_MS = 10_000
"""How long one request waits for the job: the API's own default."""
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,1023}$")
PARAMETER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
LEADING = re.compile(r"^(\s+|--[^\n]*(\n|$)|#[^\n]*(\n|$)|/\*.*?\*/)", re.DOTALL)
FIRST_WORD = re.compile(r"^([A-Za-z]+)")


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; Google's own, or a fake's."""
    project: str = ""
    """The project the queries run in."""
    dataset: str = ""
    """The dataset unqualified table names resolve to: the copy without personal fields."""
    location: str | None = None
    """Where the jobs run, where it is not a US or EU multi-region."""
    timeout: float = 30.0
    token_endpoint: str = ""
    """Where the key is exchanged, where it is neither Google's nor `<target>/token`."""

    def token(self) -> str:
        return token_endpoint(self.target, TARGET, self.token_endpoint)


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def leading_word(query: str) -> str:
    """The first word of a statement after comments and whitespace, upper case."""
    rest = query
    while True:
        found = LEADING.match(rest)
        if found is None or not found.group(0):
            break
        rest = rest[found.end() :]
    word = FIRST_WORD.match(rest)
    return word.group(1).upper() if word else ""


def _query(input: Json) -> str:
    query = input.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
        raise invalid(f"query must be a statement of at most {MAX_QUERY} characters")
    if leading_word(query) not in ("SELECT", "WITH"):
        raise invalid("query must be a SELECT: it begins with SELECT or WITH")
    return query


def _parameters(input: Json) -> list[Json]:
    given = input.get("parameters", {})
    if not isinstance(given, dict):
        raise invalid("parameters must be an object of names to text or numbers")
    out = []
    for name, value in given.items():
        if not isinstance(name, str) or PARAMETER.match(name) is None:
            raise invalid("a parameter's name is letters, digits and underscores")
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise invalid(f"parameter {name} must be text or a number")
        kind = (
            "STRING" if isinstance(value, str) else "INT64" if isinstance(value, int) else "FLOAT64"
        )
        out.append(
            {"name": name, "parameterType": {"type": kind}, "parameterValue": {"value": str(value)}}
        )
    return out


def _configured(config: Config) -> None:
    if IDENTIFIER.match(config.project) is None or IDENTIFIER.match(config.dataset) is None:
        raise invalid("the connector names no project and dataset, or not identifiers")


async def _request(
    config: Config,
    call: Call,
    token: str,
    method: str,
    path: str,
    *,
    body: Json | None = None,
    params: Json | None = None,
) -> Json:
    call.count()
    try:
        async with httpx.AsyncClient(
            base_url=config.target.rstrip("/"),
            timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout)),
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.request(method, path, json=body, params=params)
    except httpx.TimeoutException as error:
        raise unavailable(f"the warehouse did not answer in time: {type(error).__name__}") from (
            error
        )
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the token among it.
        raise unavailable(f"the warehouse could not be reached: {type(error).__name__}") from error
    status = response.status_code
    if status == 200:
        try:
            found = response.json()
        except ValueError as error:
            raise _unexpected("the warehouse answered with a body that is not JSON") from error
        if not isinstance(found, dict):
            raise _unexpected("the warehouse answered in a shape the connector does not know")
        return found
    if status == 401:
        raise TargetError(
            "unauthenticated", "none", False, "the warehouse does not admit the token"
        )
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not run this query")
    if status == 404:
        raise invalid("the warehouse knows no such project, dataset or table")
    if status == 400:
        raise invalid("the warehouse refused the query")
    if status == 429 or status >= 500:
        raise unavailable(f"the warehouse answered {status}")
    raise _unexpected(f"the warehouse answered {status}, which the connector does not foresee")


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


def _rows(found: Json, names: list[str]) -> list[Json]:
    out = []
    for row in found.get("rows") or []:
        cells = row.get("f") if isinstance(row, dict) else None
        if not isinstance(cells, list) or len(cells) != len(names):
            raise _unexpected("a row of the answer does not match its schema")
        out.append(
            {
                name: _text(cell.get("v") if isinstance(cell, dict) else None)
                for name, cell in zip(names, cells, strict=True)
            }
        )
    return out


async def run(config: Config, call: Call, input: Json) -> Outcome:
    query = _query(input)
    parameters = _parameters(input)
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    _configured(config)
    request: Json = {
        "query": query,
        "useLegacySql": False,
        "defaultDataset": {"projectId": config.project, "datasetId": config.dataset},
    }
    if parameters:
        request["parameterMode"] = "NAMED"
        request["queryParameters"] = parameters
    if config.location:
        request["location"] = config.location
    path = f"/bigquery/v2/projects/{config.project}/queries"
    token = await access_token(call, SCOPE, config.timeout, config.token())
    dry = await _request(config, call, token, "POST", path, body={**request, "dryRun": True})
    statement = dry.get("statementType")
    if statement != "SELECT":
        raise TargetError(
            "forbidden",
            "none",
            False,
            f"the warehouse calls the statement {statement or 'nothing it names'}; "
            "only a SELECT is run",
        )
    deadline = time.monotonic() + config.timeout
    found = await _request(
        config,
        call,
        token,
        "POST",
        path,
        body={**request, "maxResults": limit, "timeoutMs": WAIT_MS},
    )
    job = (found.get("jobReference") or {}).get("jobId")
    params: Json = {"timeoutMs": WAIT_MS}
    if config.location:
        params["location"] = config.location
    while not found.get("jobComplete"):
        if not isinstance(job, str) or time.monotonic() >= deadline:
            raise unavailable("the query did not complete within the connector's timeout")
        found = await _request(
            config, call, token, "GET", f"{path}/{job}", params={**params, "maxResults": limit}
        )
    fields = (found.get("schema") or {}).get("fields") or []
    if not isinstance(fields, list):
        raise _unexpected("the answer's schema is not a list of fields")
    schema = [{"name": str(f.get("name")), "type": str(f.get("type"))} for f in fields]
    names = [f["name"] for f in schema]
    rows = _rows(found, names)
    token_ = found.get("pageToken")
    pages = 1
    while token_ and len(rows) < limit and pages < MAX_PAGES and isinstance(job, str):
        page = await _request(
            config,
            call,
            token,
            "GET",
            f"{path}/{job}",
            params={**params, "maxResults": limit - len(rows), "pageToken": token_},
        )
        rows.extend(_rows(page, names))
        token_ = page.get("pageToken")
        pages += 1
    try:
        total = int(found.get("totalRows", len(rows)))
    except (TypeError, ValueError):
        total = len(rows)
    rows = rows[:limit]
    try:
        processed: int | None = int(found.get("totalBytesProcessed"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        processed = None
    output = {
        "schema": schema,
        "rows": rows,
        "total_rows": total,
        "complete": total <= len(rows),
        "bytes_processed": processed,
    }
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"warehouse.queries.run": run}
