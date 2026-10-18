# The check connector — an HTTP check

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over HTTP: one request to a path of a configured service, judged against a declared
expectation, reported with its outcome and its duration. Everywhere it is the capability
`check.http` (ADR-0111).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus.adapters.driven.connectors.httpcheck --port 9105 --target https://service.example
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
base address of the service; a call names a path under it and can reach no other host.
`--timeout` is the longest a check waits, in seconds (default 30). Added to an instance by one
entry of `TAKTUS_CONNECTORS`: `check.http=http://check-connector:9105/mcp`. A scheduled
check is a process with a schedule trigger and one step of this operation.

## What it declares

`check.http.run`, effect `read`, one request.

| Input | Meaning |
|---|---|
| `path` | the path under the service's address, starting with one `/` (default `/`) |
| `method` | `GET` (default) or `HEAD`: a check changes nothing |
| `expect.status` | one status or a list of them (default 200); a redirect is not followed |
| `expect.body_contains` | a text the body contains, read up to one MiB |
| `expect.max_duration_ms` | the longest the answer may take, to the end of the body |

The output is `outcome` (`passed` or `failed`), `status`, `duration_ms`, the `expectation` as
judged and `failures`: one `{"expected", "observed"}` for each part that did not hold. A
service that does not answer in time, or cannot be reached, is a failed check with `status`
`null`: observing that is what a check is for. Only a call the connector cannot make — a path
that is not one, an expectation that cannot hold — is an error, `invalid`, before any request.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `CHECK_TOKEN` | actions: the **requesting identity's** bearer token for the checked service; a service that admits anyone ignores it | the file `TAKTUS_CREDENTIAL_CHECK_TOKEN_FILE` names, read at the moment of each call, never stored |

The contract has no connector without the requesting identity's credential (C-03): a call
that references none is refused. The token goes to the configured service and nowhere else.
`CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9105/mcp --scenario src/taktus/adapters/driven/connectors/httpcheck/scenario.json
```

[`scenario.json`](scenario.json) checks `/health` of the fake under
`tests/fakes/metrics_service.py`, whose service paths are under `/service`; it names no write,
and C-05 passes as not applicable. `--fault NAME` breaks exactly one check
(`connectors/serving.py`); `tests/conformance/test_connector_v1_open_standards.py` runs every
fault.
