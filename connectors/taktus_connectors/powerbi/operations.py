"""How a query is asked and its rows read.

Every call first exchanges the requesting identity's pair `<client id>:<secret>` for an access
token at the identity platform, `POST /<tenant>/oauth2/v2.0/token`, a form with `client_id`,
`client_secret`, `grant_type=client_credentials` and the scope
`https://analysis.windows.net/powerbi/api/.default` (the client credentials grant). The token is
kept for that call only and sent as a bearer token.

The query is `POST /v1.0/myorg/datasets/<dataset>/executeQueries`, or
`POST /v1.0/myorg/groups/<group>/datasets/<dataset>/executeQueries` for a semantic model of a
named workspace, with the body
`{"queries": [{"query": "<DAX>"}], "serializerSettings": {"includeNulls": true}}`: one query
per call, as the API allows, and a blank value kept as null so that every row names every
column. `impersonatedUserName` is never sent. The answer is `results[0].tables[0].rows`, each
row an object from column to value, returned as the API gave it.

**Read only.** The API evaluates DAX queries and changes nothing. The query must begin with
`EVALUATE` or `DEFINE` after comments and whitespace, or it is refused unsent (`invalid`).

**Complete or not.** A query whose answer passes the API's limits (more than one table, more
than its rows or values) is answered 200 with limited rows and an `error` on the result or the
table; the rows are returned, and `complete` is false. So it is when the rows exceed the call's
`limit`.

How the provider's answers map to the contract's causes:

| Answer | Cause |
|---|---|
| the token refused (400, 401): the pair, the tenant or the scope not admitted | `unauthenticated` |
| 400: the DAX query fails | `invalid` |
| 404: no such semantic model or workspace | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the identity may not read and build on the model, or a tenant setting is off | `forbidden` |
| 429, 5xx, a refused or timed-out connection | `unavailable`, retryable: a read acted on nothing |
| any other status, a body that is not the API's | `unexpected` |

The provider's own `message` and `error_description` stay out of the error's `detail`: they
can quote the query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

TARGET = "https://api.powerbi.com"
LOGIN = "https://login.microsoftonline.com"
SCOPE = "https://analysis.windows.net/powerbi/api/.default"
LIMIT = 1000
MAX_LIMIT = 10000
MAX_QUERY = 100_000
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TENANT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}\.)*[A-Za-z0-9-]{1,63}$")
LEADING = re.compile(r"^(\s+|--[^\n]*(\n|$)|//[^\n]*(\n|$)|/\*.*?\*/)", re.DOTALL)
FIRST_WORD = re.compile(r"^([A-Za-z]+)")
STARTS = ("EVALUATE", "DEFINE")


@dataclass(frozen=True)
class Config:
    target: str = TARGET
    """The API's address; the provider's own, or a fake's."""
    login: str = LOGIN
    """The identity platform's address; the provider's own, or a fake's."""
    tenant: str = ""
    """The directory tenant the application is registered in: its identifier or domain."""
    timeout: float = 30.0


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def leading_word(query: str) -> str:
    """The first word of a query after comments and whitespace, in capitals."""
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
        raise invalid(f"query must be a DAX query of at most {MAX_QUERY} characters")
    if leading_word(query) not in STARTS:
        raise invalid("query must be a DAX query that begins with EVALUATE or DEFINE")
    return query


def _guid(input: Json, name: str, required: bool) -> str | None:
    value = input.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or GUID.match(value) is None:
        raise invalid(
            f"{name} must be an identifier of the form 00000000-0000-0000-0000-000000000000"
        )
    return value


def _limit(input: Json) -> int:
    limit = input.get("limit", LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return limit


async def _send(call: Call, client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    call.count()
    try:
        return await client.send(request)
    except httpx.TimeoutException as error:
        raise unavailable(f"the provider did not answer in time: {type(error).__name__}") from error
    except httpx.HTTPError as error:
        # The type alone: an error's text can quote the request, the secret among it.
        raise unavailable(f"the provider could not be reached: {type(error).__name__}") from error


async def _token(config: Config, call: Call, client: httpx.AsyncClient) -> str:
    client_id, colon, secret = call.token.partition(":")
    if not colon or not client_id or not secret:
        raise TargetError(
            "unauthenticated", "none", False, "the credential is not `<client id>:<secret>`"
        )
    if TENANT.match(config.tenant) is None:
        raise invalid("the connector names no tenant, or not one identifier or domain")
    request = client.build_request(
        "POST",
        f"{config.login.rstrip('/')}/{config.tenant}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": secret,
            "grant_type": "client_credentials",
            "scope": SCOPE,
        },
    )
    response = await _send(call, client, request)
    status = response.status_code
    if status in (400, 401):
        raise TargetError(
            "unauthenticated", "none", False, "the identity platform does not admit the pair"
        )
    if status == 429 or status >= 500:
        raise unavailable(f"the identity platform answered {status}")
    if status != 200:
        raise _unexpected(f"the identity platform answered {status}")
    try:
        body = response.json()
    except ValueError:
        body = None
    token = body.get("access_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise _unexpected("the identity platform answered no access token")
    return token


def _raise_for(status: int) -> None:
    if status == 401:
        raise TargetError("unauthenticated", "none", False, "the provider does not admit the token")
    if status == 403:
        raise TargetError("forbidden", "none", False, "the identity may not query this model")
    if status == 404:
        raise invalid("the provider knows no such semantic model or workspace")
    if status == 400:
        raise invalid("the provider refused the query")
    if status == 429 or status >= 500:
        raise unavailable(f"the provider answered {status}")
    raise _unexpected(f"the provider answered {status}")


def _rows(body: Any) -> tuple[list[Json], bool]:
    """The rows of the one table of the one result, and whether the API answered them all."""
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        raise _unexpected("the answer names no results")
    results = body["results"]
    if not results or not isinstance(results[0], dict):
        raise _unexpected("the answer holds no result")
    result = results[0]
    tables = result.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], dict):
        raise _unexpected("the result holds no table")
    table = tables[0]
    rows = table.get("rows")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise _unexpected("the table's rows are not objects")
    limited = any(isinstance(part.get("error"), dict) for part in (body, result, table))
    return rows, not limited and len(tables) == 1


async def query(config: Config, call: Call, input: Json) -> Outcome:
    dataset = _guid(input, "dataset", required=True)
    group = _guid(input, "group", required=False)
    dax = _query(input)
    limit = _limit(input)
    path = (
        f"/v1.0/myorg/groups/{group}/datasets/{dataset}/executeQueries"
        if group
        else f"/v1.0/myorg/datasets/{dataset}/executeQueries"
    )
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout, connect=min(10.0, config.timeout))
    ) as client:
        token = await _token(config, call, client)
        request = client.build_request(
            "POST",
            f"{config.target.rstrip('/')}{path}",
            json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}},
            headers={"Authorization": f"Bearer {token}"},
        )
        response = await _send(call, client, request)
    if response.status_code != 200:
        _raise_for(response.status_code)
    try:
        body = response.json()
    except ValueError:
        body = None
    rows, complete = _rows(body)
    output = {"rows": rows[:limit], "complete": complete and len(rows) <= limit}
    return Outcome(output=output, effect={"kind": "read"})


OPERATIONS = {"bi.figures.query": query}
